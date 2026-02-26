from utils import *

config_data = load_config()
FOCUS_DISTRICT_ID = config_data.get("focus_district_id", "17414")

def register_tools(mcp):
    """Register enrollment tools with the MCP server."""
    mcp.tool()(get_available_enrollment_years)
    mcp.tool()(get_enrollment_for_grad_cohort)
    mcp.tool()(get_enrollment_student_groups)

def get_enrollment_student_groups() -> list:
    """Get a list of all available student groups in the enrollment dataset."""
    return config_data.get("enrollment_student_groups", [])

def get_enrollment_for_grad_cohort(grad_cohorts: list, district_id: int = FOCUS_DISTRICT_ID, student_groups: list = ["All Students"]):
    """Retrieve enrollment data for specified graduation cohorts in a school district,
    including student group percentages as well as grade progression ratios.
    This function tracks student enrollment across multiple school years for cohorts
    that will graduate in specified years. For each graduation cohort, it retrieves
    enrollment data starting from kindergarten through 12th grade, following the
    cohort's progression through the school system.
    Args:
        district_id (int): The unique identifier for the school district.
        grad_cohorts (list): List of graduation cohorts to retrieve
            enrollment data for. For example, 2026 = graduating class of 2026, so the 
            results will include 12th grade enrollment in 2025-2026, 11th grade enrollment
            in 2024-2025, and so on back to kindergarten.
        student_groups (list, optional): List of student demographic groups to track
            (e.g., ["All Students", "Asian", "Hispanic"]). Defaults to ["All Students"].
            "All Students" MUST be included to calculate student group percentages correctly.
    Returns:
        list or str: A list of dictionaries containing enrollment data with the following
            fields per record:
            - schoolyear: School year (e.g., "2020-21")
            - districtname: Name of the school district
            - grad_cohort: The graduation year
            - schoolyear_num: Numeric representation of the school year
            - gradelevel_num: Numeric grade level (0-12)
            - gradelevel_str: String representation of grade level
            - {student_group}_enrollment: Total enrollment for the student group
            - {student_group}_percentage: Percentage of total enrollment for the group
            - {student_group}_progression_ratio: Grade progression ratio, comparing previous year/previous grade
              to this year (cohort retention/attrition indicator)
            Returns an error message string if the query execution fails.
    Note:
        - The query may include years beyond available data (e.g., future school years),
          which are safely excluded from results."""
    results = []
    district_name = "Unknown District"

    select_list = "`schoolyear`, `districtcode`, `districtname`"
    for student_group in student_groups:
        student_group_normalized = student_group.replace(" ", "_").lower()
        select_list += f", sum(`{student_group_normalized}`) AS `{student_group_normalized}_enrollment`"

    for grad_cohort in grad_cohorts:
        year_grade_list = ""
        # Get enrollment over time for a specified grad cohort. 
        # Example for grad cohort 2033:
        # Kindergarten (grade 0) in 2020-21 school year
        # 1st grade (grade 1) in 2021-22 school year
        # ...and so on.
        # Note: The query as built may include years that aren't in the dataset,
        # e.g. querying for grad cohort 2033 will include the 2032-33 school year,
        # which obviously there's no data for yet. This is fine, it won't cause any
        # errors, those years simply won't be present in the returned data. This
        # ensures we're always getting all available and relevant data.
        for i in range(13):
            year = grad_cohort - (12 - i)
            
            if year_grade_list:
                year_grade_list += " OR "

            year_grade_list += f"(caseless_eq(`schoolyear`, \"{get_school_year(year)}\") AND caseless_one_of(`gradelevel`, {get_grade_as_string(i)}))\n"

        query = f"""
SELECT {select_list}, {grad_cohort} as `grad_cohort`
WHERE caseless_eq(`districtcode`, '{district_id}')
AND caseless_eq(`organizationlevel`, 'District')
AND ({year_grade_list})
GROUP BY `schoolyear`, `districtcode`, `districtname`
ORDER BY `schoolyear` ASC
"""

        grad_cohort_results = execute_enrollment_query(query)

        if "error" in grad_cohort_results:
            return f"Error executing query for grad cohort {grad_cohort}: {grad_cohort_results['error']}"

        # Fix up the returned data to add some additional relevant fields.
        prev_enrollment = {}
        for grad_cohort_result in grad_cohort_results:
            grad_cohort_result["schoolyear_num"] = get_school_year_from_string(grad_cohort_result.get("schoolyear", ""))
            grad_cohort_result["gradelevel_num"] = 12 - (grad_cohort - grad_cohort_result.get("schoolyear_num", 0))
            grad_cohort_result["gradelevel_str"] = get_grade_as_string(grad_cohort_result.get("gradelevel_num", "Unknown Grade"), False)

            # Calculate percentages and grade progression ratios for each student group.
            all_students_enrollment_raw = grad_cohort_result.get("all_students_enrollment", "0")
            all_students_enrollment = int(all_students_enrollment_raw if all_students_enrollment_raw != "NULL" else "0")
            
            for student_group in student_groups:
                student_group_normalized = student_group.replace(" ", "_").lower()
                enrollment_field = f"{student_group_normalized}_enrollment"
                enrollment_raw = grad_cohort_result.get(enrollment_field, "0")
                enrollment = int(enrollment_raw if enrollment_raw != "NULL" else "0")
                
                # Calculate percentage of total student body
                if all_students_enrollment > 0:
                    percentage = (enrollment / all_students_enrollment) * 100
                    # TODO: _percentage is written for the "All Students" group in addition to any other groups.
                    # Could suppress all_students_percentage from being written if desired, since it's always 100%.
                    grad_cohort_result[f"{student_group_normalized}_percentage"] = round(percentage, 3)
                else:
                    grad_cohort_result[f"{student_group_normalized}_percentage"] = 0
                
                # Calculate grade progression ratio (current year / previous year)
                if enrollment_field in prev_enrollment:
                    prev_year_enrollment = prev_enrollment[enrollment_field]
                    if prev_year_enrollment > 0:
                        progression_ratio = enrollment / prev_year_enrollment
                        grad_cohort_result[f"{student_group_normalized}_progression_ratio"] = round(progression_ratio, 3)
                    else:
                        grad_cohort_result[f"{student_group_normalized}_progression_ratio"] = None
                else:
                    grad_cohort_result[f"{student_group_normalized}_progression_ratio"] = None
                
                # Store current enrollment for next iteration
                prev_enrollment[enrollment_field] = enrollment
            
            # We don't need this info in each individual year's record. Later on, we'll write it once for the entire dataset for this grad cohort.
            grad_cohort_result.pop("districtcode")
            district_name = grad_cohort_result.pop("districtname")
            grad_cohort_result.pop("grad_cohort")

        results.append( {
            "districtcode": district_id,
            "districtname": district_name,
            "grad_cohort": grad_cohort,
            "enrollment_data": grad_cohort_results
        })

    return results

def get_available_enrollment_years():
    """Get a list of available enrollment years."""
    years = execute_enrollment_query("SELECT `schoolyear` GROUP BY `schoolyear`")

    years_as_int = []
    for year in years:
        years_as_int.append(get_school_year_from_string(year.get("schoolyear", "")))

    return years_as_int

def execute_enrollment_query(query: str):
    """Execute a query against the enrollment dataset (single dataset for 2014-15 through current year)"""
    # TODO: Make sure enrollment_sets is properly configured.

    return execute_query(config_data["enrollment_sets"][0]["url"], query)