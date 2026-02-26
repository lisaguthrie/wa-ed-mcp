# Dumps raw benchmark score data to a JSON file, for use in testing.
from server import *

set_id = "ONE"

benchmark_scores = get_multidistrict_scores(
    multidistrict_set_id=set_id,
    subject="ELA",
    grade=3,
    student_groups=["All Students", "Low-Income", "Two or More Races", "Black/ African American"],
    years=list(range(2022, 2026))
)

with open(f"sample_{set_id}.json", "w") as f:
    json.dump(benchmark_scores, f, indent=2)