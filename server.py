from mcp.server.fastmcp import FastMCP
import json
import os
import requests
from urllib.parse import quote
import xml.etree.ElementTree as ET

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

CONFIG_FILE_NAME = "wa-ed-config.json"

mcp = FastMCP("WA Education MCP")

config_file = os.path.join(os.path.dirname(__file__), CONFIG_FILE_NAME)
with open(config_file) as f:
    config_data = json.load(f)

DISTRICTS = load_districts()

PRIMARY_DISTRICT_ID = config_data.get("primary_district_id", "17414")
DEFAULT_ASSESSMENT_YEAR = config_data.get("latest_assessment_year", 2025)

@mcp.tool()
def get_district_scores(district_ids: list = [PRIMARY_DISTRICT_ID], tests: list = ["SBAC", "AIM", "WCAS"], subject: str = "ELA", grade: int = 3, student_groups: list = ["All Students"], year: int = DEFAULT_ASSESSMENT_YEAR):
    """Get test scores for a specified list of one or more districts"""

    # Annoyingly, OSPI likes to change the name of the column that indicates the number of
    # students who were "at or above standard" (L3 or L4) in different datasets...
    met_standard_column = "count_consistent_grade_level"
    if (year < 2023):
        met_standard_column = "countmetstandard"
    elif (year in [2023, 2024]):
        met_standard_column = "count_consistent_grade_level_knowledge_and_above"

    # Same for the column with data suppression info...
    dat_column = "DAT"
    if (year < 2023):
        dat_column = "Suppression"

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
  `count_of_students_expected`,
  `{dat_column}` AS `DAT`
WHERE
  caseless_eq(`organizationlevel`, "District")
  AND caseless_eq(`gradelevel`, "{get_grade(grade)}")
  AND caseless_one_of(`testadministration`, "{get_list_as_string(tests)}")
  AND caseless_one_of(`testsubject`, "{subject}")
  AND caseless_one_of(`districtcode`, "{get_list_as_string(district_ids)}")
  AND caseless_one_of(`studentgroup`, "{get_list_as_string(student_groups)}")
  AND caseless_eq(`schoolyear`, "{get_school_year(year)}")
    """

    # Execute the query and get the JSON response
    response = execute_query(year, query)
    if "error" in response:
        return response

    # Each record in the response corresponds to a district's results for the
    # specified grade level and test subject. Each district may have more than
    # one test for a given subject (SBAC/WCAS and WA-AIM) so add together
    # the student numbers for all tests. 
    aggregated_scores = {}
    for record in response:
        studentgroup = record.get("studentgroup")
        district_id = record.get("districtcode")

        if not studentgroup:
            return {"error": "Missing studentgroup in record"}
        if not district_id:
            return {"error": "Missing districtcode in record"}

        # Create the dictionary entries for studentgroup and district_id, if
        # they don't already exist.
        if (studentgroup not in aggregated_scores):
            aggregated_scores[studentgroup] = {}
        if (district_id not in aggregated_scores[studentgroup]):
            # Initialize each district's results for each student group to 0.
            aggregated_scores[studentgroup][district_id] = {
                "total_students": 0,
                "consistent_grade_level": 0
            }

        # Add this record's student numbers to the totals for this district        
        result = aggregated_scores.get(studentgroup).get(district_id)
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
                        "district_id": district_id,
                        "year": year,
                        "record": record
                       }

    # Use the aggregated results to calculate percentages
    results = []
    for studentgroup in aggregated_scores:
        for district_id in aggregated_scores[studentgroup]:
            result_data = aggregated_scores[studentgroup][district_id]
            
            # Calculate percentage
            percent = None
            try:
                if result_data.get("total_students", 0) > 0:
                    percent = round(
                        (result_data.get("consistent_grade_level", 0) / result_data.get("total_students", 0)) * 100, 2)
            except:
                return {"error": "Error calculating percentage of students at grade level",
                        "studentgroup": studentgroup,
                        "district_id": district_id,
                        "year": year,
                        "result_data": result_data
                       }
            
            results.append({
                "student_group": studentgroup,
                "district_id": district_id,
                "total_students": result_data["total_students"],
                "consistent_grade_level": result_data["consistent_grade_level"],
                "percent_consistent_grade_level": percent
            })

    return {
        "year": year,
        "subject": subject,
        "grade": grade,
        "results": results
    }

@mcp.tool()
def analyze_benchmark_trends(focus_district_id: str = PRIMARY_DISTRICT_ID, benchmark_set_id: str = "DEFAULT", subject: str = "ELA", grade: int = 3, student_group: str = "All Students", years: list = [2022, 2023, 2024, 2025]):
    """Analyze trends in benchmark scores for a set of benchmark districts across multiple years."""
    benchmark_scores = get_benchmark_scores(
        benchmark_set_id=benchmark_set_id,
        subject=subject,
        grade=grade,
        student_groups=[student_group],
        years=years
    )
    if "error" in benchmark_scores:
        return benchmark_scores

    ranked_scores = { "ranked_results": [] }
    for year_scores in benchmark_scores.get("results", []):
        ranked_scores["ranked_results"].append(get_district_rankings(year_scores))

    return ranked_scores

def get_district_rankings(scores: dict):
    sorted_records = sorted(scores.get("data", []), key=lambda x: (x.get("percent_consistent_grade_level") is not None, x.get("percent_consistent_grade_level")), reverse=True)
    
    for rank, record in enumerate(sorted_records, start=1):
        record["rank"] = rank

    return {
        "year": scores.get("year"),
        "data_ranked": sorted_records
    }

@mcp.tool()
def get_benchmark_scores(benchmark_set_id: str = "DEFAULT", subject: str = "ELA", grade: int = 3, student_groups: list = ["All Students"], years: list = [2022, 2023, 2024, 2025]):
    """Get benchmark scores for a set of districts across multiple years."""
    benchmark_set = next((b for b in config_data["benchmark_sets"] if b["id"] == benchmark_set_id), None)
    if not benchmark_set:
        return {"error": f"Benchmark set {benchmark_set_id} not found"}

    results = { "results": [] }
    for year in years:
        scores = get_district_scores(
            district_ids=benchmark_set["districts"],
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
        "benchmark_set_id": benchmark_set_id,
        "subject": subject,
        "grade": grade,
        "student_groups": student_groups,
        "years": years,
        "results": results["results"]
    }

@mcp.tool()
def get_district_name(district_id: str = PRIMARY_DISTRICT_ID) -> dict:
    """Get the name of a district given its ID."""
    if district_id in DISTRICTS:
        return {"district_id": district_id, "district_name": DISTRICTS[district_id]}
    else:
        return {"error": f"District ID {district_id} not found"}

def get_school_year(year: int) -> str:
    """Convert a year to a school year string."""
    return f"{year-1}-{str(year)[-2:]}"

def get_grade(grade: int) -> str:
    if grade < 10:
        return f"0{grade}"
    else:
        return str(grade)

def execute_query(year: int, query_string: str) -> str:
    """Execute a query against the data.wa.gov portal for a given year and return results, with proper error handling."""
    assessment_set = next((a for a in config_data["assessment_sets"] if a["year"] == year), None)
    if not assessment_set:
        return {"error": f"Assessment dataset for year {year} not found"}
    
    query = f"{assessment_set['url']}?app_token={os.getenv('DATA_PORTAL_APP_TOKEN')}&query={quote(query_string)}"
    response = requests.get(query, timeout=10)
    try:
        response.raise_for_status() 
    except requests.exceptions.HTTPError as e:
        return {"error": str(e), "url": query, "query": query_string, "status_code": response.status_code}
    except requests.exceptions.RequestException as e:
        return {"error": str(e), "url": query, "query": query_string}

    return response.json()

def get_list_as_string(items: list) -> str:
    """Convert a list of items to a string for use in a query."""
    list_str = '","'.join(items)
    #return f"[{list_str}]"
    return list_str

@mcp.tool()
def list_benchmark_sets():
    """List available benchmark district sets."""
    return config_data["benchmark_sets"]

@mcp.tool()
def list_available_years():
    """List all available assessment years."""
    return [a["year"] for a in config_data["assessment_sets"]]

@mcp.tool()
def list_available_tests(year: int = DEFAULT_ASSESSMENT_YEAR):
    """List all available test/subject pairs for a given year."""
    query = """SELECT `testadministration`, `testsubject`, `gradelevel`
GROUP BY `testadministration`, `testsubject`, `gradelevel`
HAVING caseless_ne(`gradelevel`, "All Grades")"""
    response = execute_query(year, query)
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

    return execute_query(year, query)

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

if __name__ == "__main__":
    mcp.run(transport="stdio")
