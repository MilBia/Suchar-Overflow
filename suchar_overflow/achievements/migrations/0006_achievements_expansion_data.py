from django.db import migrations

def create_expansion_achievements(apps, schema_editor):
    Achievement = apps.get_model("achievements", "Achievement")

    ICON_STAR = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-star-fill" viewBox="0 0 16 16"><path d="M3.612 15.443c-.386.198-.824-.149-.746-.592l.83-4.73L.173 6.765c-.329-.314-.158-.888.283-.95l4.898-.696L7.538.792c.197-.39.73-.39.927 0l2.184 4.327 4.898.696c.441.062.612.636.282.95l-3.522 3.356.83 4.73c.078.443-.36.79-.746.592L8 13.187l-4.389 2.256z"/></svg>"""
    ICON_THUMBS_UP = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-hand-thumbs-up-fill" viewBox="0 0 16 16"><path d="M6.956 1.745C7.021.81 7.908.087 8.864.325l.261.066c.463.116.874.456 1.012.965.22.816.533 2.511.062 4.51a10 10 0 0 1 .443-.051c.713-.065 1.669-.072 2.516.21.518.173.994.681 1.2 1.273.184.532.16 1.162-.234 1.733.058.119.103.242.138.363.077.27.113.567.113.856s-.036.586-.113.856c-.039.135-.09.273-.16.404.169.387.107.819-.003 1.148a3.2 3.2 0 0 1-.488.901c.054.152.076.312.076.465 0 .305-.2.519-.3.589-.127.09-.344.232-.715.429-.474.252-1.31.622-2.78.622-1.47 0-2.286-.927-2.704-1.306-.322-.29-.594-.593-.895-.877l-.6-.575-.125-.119-.06-.057a6.2 6.2 0 0 0-.276-.237C5.46 11.231 4.7 10.991 4 10.991S0 11.5 0 11.5V5.5S1.79 3 4 3c1.737 0 3.012.723 3.962 1.343.327-.47.64-1.076.994-2.598"/></svg>"""
    ICON_FIRE = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-fire" viewBox="0 0 16 16"><path d="M8 16c3.314 0 6-2 6-5.5 0-1.5-.5-4-2.5-6 .25 1.5-1.25 2-1.25 2C11 4 9 .5 6 0c.357 2 .5 4-2 6-1.25 1-2 2.729-2 4.5C2 14 4.686 16 8 16m0-1c-1.657 0-3-1-3.275-3.275C5.507 14.507 9 14.507 9 11.725 9.275 14 8 15 8 15"/></svg>"""
    ICON_MOON = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-moon-stars-fill" viewBox="0 0 16 16"><path d="M6 .278a.768.768 0 0 1 .08.858 7.208 7.208 0 0 0-.878 3.46c0 4.021 3.278 7.277 7.318 7.277.527 0 1.04-.055 1.533-.16a.787.787 0 0 1 .81.316.733.733 0 0 1-.031.893A8.349 8.349 0 0 1 8.344 16C3.734 16 0 12.286 0 7.71 0 4.266 2.114 1.312 5.124.06A.752.752 0 0 1 6 .278z"/></svg>"""
    ICON_CALENDAR = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-calendar-check" viewBox="0 0 16 16"><path d="M10.854 7.146a.5.5 0 0 1 0 .708l-3 3a.5.5 0 0 1-.708 0l-1.5-1.5a.5.5 0 1 1 .708-.708L7.5 9.793l2.646-2.647a.5.5 0 0 1 .708 0z"/><path d="M3.5 0a.5.5 0 0 1 .5.5V1h8V.5a.5.5 0 0 1 1 0V1h1a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V3a2 2 0 0 1 2-2h1V.5a.5.5 0 0 1 .5-.5zM1 4v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V4H1z"/></svg>"""
    ICON_DROP = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-droplet-half" viewBox="0 0 16 16"><path fill-rule="evenodd" d="M7.21.8C7.69.295 8 0 8 0c.109.363.234.708.371 1.038.812 1.946 2.073 3.35 3.197 4.6C12.878 7.096 14 8.345 14 10a6 6 0 0 1-12 0C2 6.668 5.58 2.517 7.21.8zm.413 1.021A31.259 31.259 0 0 0 5.794 3.99c-1.573 2.046-3.792 5.353-3.792 6.01a5.992 5.992 0 0 0 4 5.657z"/></svg>"""
    ICON_YIN_YANG = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-yin-yang" viewBox="0 0 16 16"><path d="M9.167 4.5a1.167 1.167 0 1 1-2.334 0 1.167 1.167 0 0 1 2.334 0Z"/><path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0ZM1 8a7 7 0 0 1 7-7 3.5 3.5 0 1 1 0 7 3.5 3.5 0 1 0 0 7 7 7 0 0 1-7-7Zm7 4.667a1.167 1.167 0 1 1 0-2.334 1.167 1.167 0 0 1 0 2.334Z"/></svg>"""

    TIERS = [1, 2, 3, 4, 5]
    TIER_LABELS = ["Brąz", "Srebro", "Złoto", "Platyna", "Diament"]

    def create_series(base_name, slug_prefix, description_template, icon, category, event_type, metric, theme, thresholds, secret_idx_start=99):
        for idx, threshold in enumerate(thresholds):
            tier = TIERS[idx]
            tier_label = TIER_LABELS[idx]
            
            is_secret = idx >= secret_idx_start
            
            nav_desc = description_template.format(threshold)
            Achievement.objects.update_or_create(
                slug=f"{slug_prefix}-{tier_label.lower()}",
                defaults={
                    "name": f"{base_name} ({tier_label})",
                    "description": nav_desc,
                    "icon_content": icon,
                    "category": category,
                    "event_type": event_type,
                    "metric": metric,
                    "threshold": threshold,
                    "theme": theme,
                    "tier": tier,
                    "is_secret": is_secret,
                }
            )

    # 1. Twórca Sucharów
    create_series(
        "Królowa/Król Sucharów", "suchar-creator",
        "Wstaw {} sucharów.", ICON_STAR, "LIFETIME", "SUCHAR_POSTED", "COUNT_SUCHAR", "Twórca",
        [1, 25, 100, 250, 500]
    )

    # 2. Koneser Głosów
    create_series(
        "Znawca Suszy", "vote-caster",
        "Oddaj {} głosów pod różnymi sucharami.", ICON_THUMBS_UP, "LIFETIME", "VOTE_CAST", "COUNT_VOTE_CAST", "Aktywista",
        [1, 50, 250, 1000, 5000]
    )

    # 3. Popularność (Rozchwytywany)
    create_series(
        "Gwiazda Sceny", "rising-star-serie",
        "Uzyskaj ogólny bilans {} punktów popularności ze wszystkich Twoich sucharów.", ICON_FIRE, "LIFETIME", "VOTE_RECEIVED", "SUM_SCORE", "Rozgłos",
        [10, 50, 200, 500, 1000]
    )

    # 4. Nocna Sowa
    create_series(
        "Nocna Sowa", "night-owl",
        "Zarwij nockę i opublikuj {} sucharów pomiędzy północą a 4 w nocy.", ICON_MOON, "LIFETIME", "SUCHAR_POSTED", "NIGHT_OWL", "Nocny Marek",
        [1, 10, 50, 100, 365],
        secret_idx_start=3 # Platyna i Diament tajne
    )

    # 5. Recydywista
    create_series(
        "Recydywista", "streak-login",
        "Posiadaj aktywność logowania {} dni z rzędu na naszej platformie.", ICON_CALENDAR, "STREAK", "SUCHAR_POSTED", "STREAK_LOGIN", "Streaki",
        [3, 7, 14, 30, 100],
        secret_idx_start=4 # Diament na 100 dni jest tajny
    )

    # 6. Grzybiarz (Same odznaki na MINUSY)
    create_series(
        "Grzybiarz", "vote-dry-koneser",
        "Oddaj {} suchych głosów w historii swojej kariery.", ICON_DROP, "LIFETIME", "VOTE_CAST", "COUNT_VOTE_DRY", "Susza",
        [1, 50, 200, 500, 2000]
    )

    # 7. Polaryzator (Równa liczba głosów - jak gracz podpowiedział ukrywamy WSZYSTKIE i progi do 50)
    create_series(
        "Polaryzator", "polarizer-master",
        "Odnajdź balans dzieląc społeczność idealnie w pół przy {} ocenach.", ICON_YIN_YANG, "LIFETIME", "VOTE_RECEIVED", "POLARIZER", "Kontrowersja",
        [1, 5, 10, 25, 50],
        secret_idx_start=0 # Od samego Brązu ściśle tajna drabinowatość
    )

class Migration(migrations.Migration):

    dependencies = [
        ('achievements', '0005_achievement_is_secret'),
    ]

    operations = [
        migrations.RunPython(create_expansion_achievements, migrations.RunPython.noop)
    ]
