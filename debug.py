import os
import json
import sys
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
import enrollment_tools
from utils import *

load_dotenv()

# Now call the function you want to debug
if __name__ == "__main__":
    enrollment_tools.get_enrollment_for_grad_cohort(district_id=17414, grad_cohorts=[2028, 2030], student_groups=["all_students", "low_income"])