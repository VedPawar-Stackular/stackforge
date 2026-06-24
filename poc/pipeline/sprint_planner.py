"""
Sprint assignment — Stage 3, Step 1.

Assigns user stories to sprints using greedy bin-packing ordered by descending
story points. Zero LLM calls — this is a deterministic rule-based operation.

TOKEN OPTIMIZATION:
  Sprint scheduling is a capacity-packing problem, not a reasoning problem.
  A greedy bin-packing algorithm produces near-optimal sprint plans without
  any LLM involvement. This step costs $0 in API calls.

  The naive alternative — asking Opus to "plan our sprints" — would:
    - Cost ~$0.02-0.04 per planning run
    - Produce non-deterministic, hard-to-validate output
    - Add latency with no quality improvement over math

  Rule: if the answer is deterministic and algorithmic, don't use an LLM.
"""


def assign_stories_to_sprints(
    stories: list[dict],
    capacity: int = 20,
) -> list[dict]:
    """
    Assign user stories to sprints via greedy bin-packing.

    Stories are sorted descending by story_points so larger stories are placed
    first, which maximises sprint utilisation (classic first-fit decreasing).
    Stories without a point estimate default to 3 points.

    Returns a list of sprint dicts:
      [{"number": 1, "stories": [...], "total_points": 18, "capacity": 20}, ...]

    Each story dict in the returned list retains all original fields.
    """
    if not stories:
        return []

    DEFAULT_POINTS = 3

    # Sort descending so large stories are packed first (first-fit decreasing)
    sorted_stories = sorted(
        stories,
        key=lambda s: (s.get("story_points") or DEFAULT_POINTS),
        reverse=True,
    )

    sprints: list[dict] = []
    current_stories: list[dict] = []
    current_points: int = 0
    sprint_num: int = 1

    for story in sorted_stories:
        pts = story.get("story_points") or DEFAULT_POINTS

        # If story alone exceeds capacity, place it in its own sprint
        if pts > capacity:
            if current_stories:
                sprints.append(_make_sprint(sprint_num, current_stories, current_points, capacity))
                sprint_num += 1
                current_stories = []
                current_points = 0
            sprints.append(_make_sprint(sprint_num, [story], pts, capacity))
            sprint_num += 1
            continue

        # If adding this story would exceed capacity, close current sprint
        if current_points + pts > capacity and current_stories:
            sprints.append(_make_sprint(sprint_num, current_stories, current_points, capacity))
            sprint_num += 1
            current_stories = []
            current_points = 0

        current_stories.append(story)
        current_points += pts

    # Close the final sprint
    if current_stories:
        sprints.append(_make_sprint(sprint_num, current_stories, current_points, capacity))

    return sprints


def _make_sprint(number: int, stories: list[dict], total_points: int, capacity: int) -> dict:
    return {
        "number": number,
        "name": f"Sprint {number}",
        "stories": stories,
        "total_points": total_points,
        "capacity_points": capacity,
    }
