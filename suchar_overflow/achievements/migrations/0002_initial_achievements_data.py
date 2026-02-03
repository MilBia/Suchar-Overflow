from django.db import migrations

def create_initial_achievements(apps, schema_editor):
    Achievement = apps.get_model("achievements", "Achievement")

    # SVG Definitions (Simplified for example, real ones would be more complex)
    ICON_STAR = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-star-fill" viewBox="0 0 16 16"><path d="M3.612 15.443c-.386.198-.824-.149-.746-.592l.83-4.73L.173 6.765c-.329-.314-.158-.888.283-.95l4.898-.696L7.538.792c.197-.39.73-.39.927 0l2.184 4.327 4.898.696c.441.062.612.636.282.95l-3.522 3.356.83 4.73c.078.443-.36.79-.746.592L8 13.187l-4.389 2.256z"/></svg>"""
    ICON_THUMBS_UP = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-hand-thumbs-up-fill" viewBox="0 0 16 16"><path d="M6.956 1.745C7.021.81 7.908.087 8.864.325l.261.066c.463.116.874.456 1.012.965.22.816.533 2.511.062 4.51a10 10 0 0 1 .443-.051c.713-.065 1.669-.072 2.516.21.518.173.994.681 1.2 1.273.184.532.16 1.162-.234 1.733.058.119.103.242.138.363.077.27.113.567.113.856s-.036.586-.113.856c-.039.135-.09.273-.16.404.169.387.107.819-.003 1.148a3.2 3.2 0 0 1-.488.901c.054.152.076.312.076.465 0 .305-.2.519-.3.589-.127.09-.344.232-.715.429-.474.252-1.31.622-2.78.622-1.47 0-2.286-.927-2.704-1.306-.322-.29-.594-.593-.895-.877l-.6-.575-.125-.119-.06-.057a6.2 6.2 0 0 0-.276-.237C5.46 11.231 4.7 10.991 4 10.991S0 11.5 0 11.5V5.5S1.79 3 4 3c1.737 0 3.012.723 3.962 1.343.327-.47.64-1.076.994-2.598"/></svg>"""
    ICON_FIRE = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-fire" viewBox="0 0 16 16"><path d="M8 16c3.314 0 6-2 6-5.5 0-1.5-.5-4-2.5-6 .25 1.5-1.25 2-1.25 2C11 4 9 .5 6 0c.357 2 .5 4-2 6-1.25 1-2 2.729-2 4.5C2 14 4.686 16 8 16m0-1c-1.657 0-3-1-3.275-3.275C5.507 14.507 9 14.507 9 11.725 9.275 14 8 15 8 15"/></svg>"""

    # 1. First Suchar
    # Event: SUCHAR_POSTED
    # Metric: COUNT_SUCHAR >= 1
    # Category: LIFETIME
    Achievement.objects.get_or_create(
        name="First Suchar",
        slug="first-suchar",
        description="Posted your first Suchar!",
        icon_content=ICON_STAR,
        category="LIFETIME",  # Hardcoded string to match TextChoices
        event_type="SUCHAR_POSTED",
        metric="COUNT_SUCHAR",
        threshold=1
    )

    # 2. First Vote
    # Event: VOTE_CAST
    # Metric: COUNT_VOTE_CAST >= 1
    # Category: LIFETIME
    Achievement.objects.get_or_create(
        name="First Vote",
        slug="first-vote",
        description="Cast your first vote!",
        icon_content=ICON_THUMBS_UP,
        category="LIFETIME",
        event_type="VOTE_CAST",
        metric="COUNT_VOTE_CAST",
        threshold=1
    )

    # 3. Popular Suchar (5 Votes)
    # Event: VOTE_RECEIVED (Target user: Author)
    # Metric: SUM_SCORE >= 5 (Simplified requirement: total votes received on all suchars or single suchar? 
    # Logic engine implements 'SUM_SCORE' as sum of votes on all suchars.
    # If we want "One suchar reached 5 votes", that's a different metric.
    # Current engine implementation: current_value = sum(s.votes.count() for s in user.suchary.all()
    # So this is "Total 5 votes received across all suchars".
    # Let's stick to that for now as per code or adjust description.
    Achievement.objects.get_or_create(
        name="Rising Star",
        slug="rising-star",
        description="Received 5 votes in total!",
        icon_content=ICON_FIRE,
        category="LIFETIME",
        event_type="VOTE_RECEIVED",
        metric="SUM_SCORE",
        threshold=5
    )

    # 4. Best of Month
    # Event: PERIODIC
    # Metric: PERIOD_WIN
    # Category: PERIODIC
    # Note: These use manual assignment via management command, so event_type/metric are placeholders or specific types.
    # Currently Engine only handles 'VOTE_CAST', 'SUCHAR_POSTED'. 
    # Valid EventTypes in code: SUCHAR_POSTED, VOTE_RECEIVED, VOTE_CAST.
    # We should add PERIODIC_AWARD to choices if we want strict validation, 
    # but for now we can just store them. The engine won't auto-trigger them, which is correct.
    
    Achievement.objects.get_or_create(
        name="Comedian of the Month",
        slug="best-suchar-month",
        description="Posted the highest rated Suchar of the month!",
        icon_content="""<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-calendar-check" viewBox="0 0 16 16"><path d="M10.854 7.146a.5.5 0 0 1 0 .708l-3 3a.5.5 0 0 1-.708 0l-1.5-1.5a.5.5 0 1 1 .708-.708L7.5 9.793l2.646-2.647a.5.5 0 0 1 .708 0z"/><path d="M3.5 0a.5.5 0 0 1 .5.5V1h8V.5a.5.5 0 0 1 1 0V1h1a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V3a2 2 0 0 1 2-2h1V.5a.5.5 0 0 1 .5-.5zM1 4v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V4H1z"/></svg>""",
        category="PERIODIC",
        event_type="SUCHAR_POSTED", # Placeholder
        metric="SUM_SCORE", # Placeholder
        threshold=0
    )

    # 5. Best of Year
    Achievement.objects.get_or_create(
        name="Legend of the Year",
        slug="best-suchar-year",
        description="Posted the highest rated Suchar of the year!",
        icon_content="""<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-trophy" viewBox="0 0 16 16"><path d="M2.5.5A.5.5 0 0 1 3 0h10a.5.5 0 0 1 .5.5c0 .538-.012 1.05-.034 1.536a3 3 0 1 1-1.133 5.89c-.79 1.865-1.878 2.777-2.833 3.011v2.173l1.425.356c.194.048.377.135.537.255L13.3 15.1a.5.5 0 0 1-.3.9H3a.5.5 0 0 1-.3-.9l1.838-1.379c.16-.12.343-.207.537-.255L6.5 13.11v-2.173c-.955-.234-2.043-1.146-2.833-3.012a3 3 0 1 1-1.132-5.89A33.076 33.076 0 0 1 2.5.5zm.099 2.54a2 2 0 0 0 .72 3.935c-.333-1.05-.588-2.346-.72-3.935zm10.083 3.935a2 2 0 0 0 .72-3.935c-.133 1.589-.388 2.885-.72 3.935zM3.504 1c.007.517.026 1.006.056 1.469.13 2.028.457 3.546.87 4.667C5.294 9.48 6.484 10 7 10a.5.5 0 0 1 .168.545L6.051 14.5a.5.5 0 0 1-.9.132l-1.838-1.38a.5.5 0 0 0-.583-.008l-1.838 1.38a.5.5 0 0 1-.9-.132l-1.117-3.955A.5.5 0 0 1 0 10c.516 0 1.706-.52 2.57-2.864.413-1.12.74-2.64.87-4.667.03-.463.049-.952.056-1.469h10.008z"/></svg>""",
        category="PERIODIC",
        event_type="SUCHAR_POSTED",
        metric="SUM_SCORE",
        threshold=0
    )

class Migration(migrations.Migration):

    dependencies = [
        ("achievements", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_initial_achievements, migrations.RunPython.noop),
    ]
