from mcp.server.fastmcp import FastMCP
import json
import os
#import requests
#from urllib.parse import quote
import xml.etree.ElementTree as ET
from collections import defaultdict
import enrollment_tools
from utils import *

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

mcp = FastMCP("WA Education MCP")

config_data = load_config()

def load_districts():
    """Load district codes and names for easy querying"""
    districts = {}
    tree = ET.parse(os.path.join(os.path.dirname(__file__), "Districts.xml"))
    root = tree.getroot()
    for row in root.findall(".//row"):
        code = row.findtext("districtcode")
        name = row.findtext("districtname")
        if code and name:
            districts[code] = name
    return districts

DISTRICTS = load_districts()

FOCUS_DISTRICT_ID = config_data.get("focus_district_id", "17414")
DEFAULT_ASSESSMENT_YEAR = config_data.get("latest_assessment_year", 2025)

enrollment_tools.register_tools(mcp)

@mcp.tool()
def get_district_scores(district_ids: list = [FOCUS_DISTRICT_ID], tests: list = ["SBAC", "AIM", "WCAS"], subject: str = "ELA", grade: int = 3, student_groups: list = ["All Students"], year: int = DEFAULT_ASSESSMENT_YEAR):
    """Get raw test scores for a specified list of one or more districts. Do NOT manually compute rankings or trends using this raw data. Use analyze_benchmark_trends or analyze_district_trends instead."""
    # Annoyingly, the data in the various annual datasets is essentially unchanged, but OSPI likes to change
    # around column names. Here we normalize the column names we need to use based on year.
    met_standard_column = "count_consistent_grade_level"
    total_students_column = "count_of_students_expected"
    dat_column = "DAT"
    grade_adjusted = grade
    if (year == 2021):
        met_standard_column = "numeratorsuppressed"
        total_students_column = "denominatorsuppressed"
        dat_column = "Suppression"
        # 2020-21 data is extra-funky because the test was given in the fall of 2021, rather than the spring
        # (due to COVID-19). So the students were a grade level older than expected, i.e. the kids who took
        # the 3rd grade test are listed as 4th graders in the data. Adjust accordingly to match other years.
        grade_adjusted = grade + 1
    elif (year < 2023):
        met_standard_column = "countmetstandard"
        dat_column = "Suppression"
    elif (year in [2023, 2024]):
        met_standard_column = "count_consistent_grade_level_knowledge_and_above"

    # Also annoyingly, the "two or more races" student group is sometimes called TwoorMoreRaces.
    # If there is a student group that starts with "Two" then make sure both versions are added.
    if any(group.startswith("Two") for group in student_groups):
        student_groups = student_groups.copy() # work with a copy to avoid modifying caller's list
        student_groups.append("TwoorMoreRaces")
        student_groups.append("Two Or More Races")

    # Define the query to use against the data.wa.gov portal
    query = f"""SELECT
  `schoolyear`,
  `organizationlevel`,
  `districtcode`,
  `districtname`,
  `studentgroup`,
  `studentgrouptype`,
  `gradelevel`,
  `testadministration`,
  `testsubject`,
  `{met_standard_column}` AS `count_consistent_grade_level`,
  `{total_students_column}` AS `count_of_students_expected`,
  `{dat_column}` AS `DAT`
WHERE
  caseless_eq(`organizationlevel`, "District")
  AND caseless_eq(`gradelevel`, "{get_grade(grade_adjusted)}")
  AND caseless_one_of(`testadministration`, "{get_list_as_string(tests)}")
  AND caseless_one_of(`testsubject`, "{subject}")
  AND caseless_one_of(`districtcode`, "{get_list_as_string(district_ids)}")
  AND caseless_one_of(`studentgroup`, "{get_list_as_string(student_groups)}")
  AND caseless_eq(`schoolyear`, "{get_school_year(year)}")
    """

    # Execute the query and get the JSON response
    response = execute_assessment_query(year, query)
    if "error" in response:
        return response

    # Each record in the response corresponds to a district's results for the
    # specified grade level and test subject. Each district may have more than
    # one test for a given subject (SBAC/WCAS and WA-AIM) so add together
    # the student numbers for all tests. 
    aggregated_scores = {}
    for record in response:
        studentgroup = record.get("studentgroup")
        studentgroup_adjusted = studentgroup
        if studentgroup == "TwoorMoreRaces":
            studentgroup_adjusted = "Two Or More Races"
        district_id = record.get("districtcode")

        if not studentgroup:
            return {"error": "Missing studentgroup in record"}
        if not district_id:
            return {"error": "Missing districtcode in record"}

        # Create the dictionary entries for studentgroup and district_id, if
        # they don't already exist.
        if (studentgroup_adjusted not in aggregated_scores):
            aggregated_scores[studentgroup_adjusted] = {}
        if (district_id not in aggregated_scores[studentgroup_adjusted]):
            # Initialize each district's results for each student group to 0.
            aggregated_scores[studentgroup_adjusted][district_id] = {
                "total_students": 0,
                "consistent_grade_level": 0
            }

        # Add this record's student numbers to the totals for this district
        result = aggregated_scores.get(studentgroup_adjusted).get(district_id)
        if result:
            total_str = record.get("count_of_students_expected", "0")
            if total_str == "NULL": total_str = "0"
            consistent_str = record.get("count_consistent_grade_level", "0")
            if consistent_str == "NULL": consistent_str = "0"
            try:
                result["total_students"] += int(total_str)
                result["consistent_grade_level"] += int(consistent_str)
            except:
                return {"error": "Error converting student counts to integers",
                        "studentgroup": studentgroup,
                        "studentgroup_adjusted": studentgroup_adjusted,
                        "district_id": district_id,
                        "year": year,
                        "record": record
                       }

    # Use the aggregated results to calculate percentages
    results = []
    for studentgroup_adjusted in aggregated_scores:
        for district_id in aggregated_scores[studentgroup_adjusted]:
            result_data = aggregated_scores[studentgroup_adjusted][district_id]
            # Calculate percentage
            percent = None
            try:
                if result_data.get("total_students", 0) > 0:
                    percent = round(
                        (result_data.get("consistent_grade_level", 0) / result_data.get("total_students", 0)) * 100, 2)
            except:
                return {"error": "Error calculating percentage of students at grade level",
                        "studentgroup": studentgroup,
                        "studentgroup_adjusted": studentgroup_adjusted,
                        "district_id": district_id,
                        "year": year,
                        "result_data": result_data
                       }

            results.append({
                "student_group": studentgroup_adjusted,
                "district_id": district_id,
                "total_students": result_data["total_students"],
                "consistent_grade_level": result_data["consistent_grade_level"],
                "percent_consistent_grade_level": percent
            })

    return {
        "year": year,
        "subject": subject,
        "grade": grade,
        "results": results,
        "query": query
    }

@mcp.tool()
def analyze_trends(focus_district_id: str = FOCUS_DISTRICT_ID, multidistrict_set_id: str = "DEFAULT", subject: str = "ELA", grade: int = 3, student_groups: list = ["All Students", "Low-Income"], year: int = DEFAULT_ASSESSMENT_YEAR, yearspan: int = 4):
    """Analyze trends in scores for one or more districts across multiple years. Returns authoritative rankings across multiple districts and trends across multiple years. Use this tool whenever multi-district ranking or trend logic is required. Do NOT compute rankings or trends manually."""
    first_year = year - yearspan + 1
    last_year = year

    if (first_year <= 2020 and last_year > 2020): # adjust for no state testing in 2020
        first_year = first_year - 1
        yearspan = yearspan + 1

    benchmark_scores = get_multidistrict_scores(
        multidistrict_set_id=multidistrict_set_id,
        subject=subject,
        grade=grade,
        student_groups=student_groups,
        years=list(range(first_year, last_year + 1))
    )
    if "error" in benchmark_scores:
        return benchmark_scores

    analysis = { "ranked_results": [], "annual_trends": [] }
    for student_group in benchmark_scores.get("student_groups", []):
        for year_scores in benchmark_scores.get("results", []):
            analysis["ranked_results"].append(get_district_rankings(year_scores, student_group))

        analysis["annual_trends"].append(get_annual_trends(benchmark_scores, first_year, last_year, student_group))

    return analysis

def get_annual_trends(scores: dict, first_year, last_year, student_group) -> dict:
    first_year_scores = next((record for record in scores.get("results", []) if record.get("year") == first_year), None)
    last_year_scores = next((record for record in scores.get("results", []) if record.get("year") == last_year), None)

    trends_by_district = []

    for last_record in last_year_scores.get("data", []):
        if last_record.get("student_group") != student_group:
            continue

        district_id = last_record.get("district_id")
        first_record = next((r for r in first_year_scores.get("data", []) if r.get("district_id") == district_id and r.get("student_group") == student_group), None)
        if not first_record:
            continue

        first_percent = first_record.get("percent_consistent_grade_level", None)
        last_percent = last_record.get("percent_consistent_grade_level", None)

        if first_percent is None or last_percent is None:
            continue

        annual_trend = (last_percent - first_percent) / (last_year - first_year + 1)

        trends_by_district.append({
            "district_id": district_id,
            "first_year_percent": first_percent,
            "last_year_percent": last_percent,
            "annual_trend": round(annual_trend, 2)
        })

    return {
        "student_group": student_group,
        "first_year": first_year,
        "last_year": last_year,
        "trends_by_district": trends_by_district
    }

def get_district_rankings(scores: dict, student_group: str) -> dict:
    # Filter scores to only include the specified student group. Make copies of each record tnat we include,
    # so we don't modify the original data.
    filtered_scores = [record.copy() for record in scores.get("data", []) if record.get("student_group", "Unknown") == student_group]

    sorted_records = sorted(filtered_scores, key=lambda x: (x.get("percent_consistent_grade_level") is not None, x.get("percent_consistent_grade_level")), reverse=True)

    for rank, record in enumerate(sorted_records, start=1):
        record["rank"] = rank
        record.pop("student_group", None)  # remove redundant student_group field

    return {
        "year": scores.get("year"),
        "student_group": student_group,
        "ranked_data": sorted_records
    }

def get_multidistrict_scores(multidistrict_set_id: str = "DEFAULT", subject: str = "ELA", grade: int = 3, student_groups: list = ["All Students"], years: list = [2022, 2023, 2024, 2025]):
    """Get scores for a set of multiple districts across multiple years."""
    multidistrict_set = next((b for b in config_data["multidistrict_sets"] if b["id"] == multidistrict_set_id), None)
    if not multidistrict_set:
        return {"error": f"Multidistrict set {multidistrict_set_id} not found"}
    results = { "results": [] }
    for year in years:
        if year == 2020: # skip 2020, no testing data
            continue

        scores = get_district_scores(
            district_ids=multidistrict_set["districts"],
            subject=subject,
            grade=grade,
            student_groups=student_groups,
            year=year
        )
        if "error" in scores:
            return scores

        results["results"].append({
            "year": year,
            "data": scores["results"]
        })

    return {
        "multidistrict_set_id": multidistrict_set_id,
        "subject": subject,
        "grade": grade,
        "student_groups": student_groups,
        "years": years,
        "results": results["results"]
    }

@mcp.tool()
def get_district_name(district_id: str = FOCUS_DISTRICT_ID) -> dict:
    """Get the name of a district given its ID."""
    if district_id in DISTRICTS:
        return {"district_id": district_id, "district_name": DISTRICTS[district_id]}
    else:
        return {"error": f"District ID {district_id} not found"}

def get_grade(grade: int) -> str:
    if grade < 10:
        return f"0{grade}"
    else:
        return str(grade)

def execute_assessment_query(year: int, query_string: str) -> dict:
    """Execute a query against the data.wa.gov portal for a given year and return results, with proper error handling."""
    assessment_set = next((a for a in config_data["assessment_sets"] if a["year"] == year), None)
    if not assessment_set:
        return {"error": f"Assessment dataset for year {year} not found"}
    
    return execute_query(assessment_set["url"], query_string)

def get_list_as_string(items: list) -> str:
    """Convert a list of items to a string for use in a query."""
    list_str = '","'.join(items)
    #return f"[{list_str}]"
    return list_str

@mcp.tool()
def list_multidistrict_sets():
    """List available multidistrict sets."""
    return config_data["multidistrict_sets"]

@mcp.tool()
def get_multidistrict_set(multidistrict_set_id: str) -> dict:
    """Get details of a specific multidistrict set."""
    multidistrict_set = next((b for b in config_data["multidistrict_sets"] if b["id"] == multidistrict_set_id), None)
    if not multidistrict_set:
        return {"error": f"Multidistrict set {multidistrict_set_id} not found"}
    return multidistrict_set

@mcp.tool()
def list_available_assessment_years():
    """List all available assessment years."""
    return [a["year"] for a in config_data["assessment_sets"]]

@mcp.tool()
def list_available_tests(year: int = DEFAULT_ASSESSMENT_YEAR):
    """List all available test/subject pairs for a given year."""
    query = """SELECT `testadministration`, `testsubject`, `gradelevel`
GROUP BY `testadministration`, `testsubject`, `gradelevel`
HAVING caseless_ne(`gradelevel`, "All Grades")"""
    response = execute_assessment_query(year, query)
    if "error" in response:
        return response
    
    for test in response:
        test["gradelevel"] = int(test["gradelevel"])

    return response

@mcp.tool()
def list_available_student_groups(year: int = DEFAULT_ASSESSMENT_YEAR):
    """List all available student groups for a given year."""
    query = """SELECT `studentgroup`, `studentgrouptype`
GROUP BY `studentgrouptype`, `studentgroup`
ORDER BY `studentgrouptype`"""

    return execute_assessment_query(year, query)

if __name__ == "__main__":
    mcp.run(transport="stdio")
