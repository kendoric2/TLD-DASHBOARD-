"""Sample data used in DEMO mode (when no TLDCRM credentials are configured)."""


def get_sample_dashboard(range_label="This Month"):
    return {
        "demo": True,
        "range_label": range_label,
        "kpis": {
            "policies_sold": 312,
            "billable_leads": 1840,
            "conversion_rate": 16.9,
            "avg_gtl_premium": 1562,
        },
        "by_carrier": [
            {"label": "Aetna", "count": 87},
            {"label": "UnitedHealthcare", "count": 75},
            {"label": "Humana", "count": 59},
            {"label": "Cigna", "count": 44},
            {"label": "WellCare", "count": 28},
            {"label": "Other", "count": 19},
        ],
        "by_plan": [
            {"label": "Medicare Advantage", "count": 186},
            {"label": "Medicare Supplement", "count": 84},
            {"label": "Prescription Drug (PDP)", "count": 42},
        ],
        "recent_sales": [
            {"date_sold": "Jun 24", "agent": "Maria Alvarez", "product": "Medicare Advantage", "carrier": "Aetna", "premium": None, "status": "issued"},
            {"date_sold": "Jun 24", "agent": "David Chen", "product": "Med Supp Plan G", "carrier": "UnitedHealthcare", "premium": None, "status": "submitted"},
            {"date_sold": "Jun 24", "agent": "Sarah Johnson", "product": "Final Expense", "carrier": "Guarantee Trust Life", "premium": 1560, "status": "issued"},
            {"date_sold": "Jun 23", "agent": "James Okafor", "product": "Medicare Advantage", "carrier": "Cigna", "premium": None, "status": "pending"},
            {"date_sold": "Jun 23", "agent": "Priya Patel", "product": "Medicare Advantage", "carrier": "WellCare", "premium": None, "status": "issued"},
            {"date_sold": "Jun 23", "agent": "Luis Romero", "product": "Med Supp Plan N", "carrier": "Humana", "premium": None, "status": "submitted"},
        ],
        "agents": [
            {"name": "Maria Alvarez", "calls": 412, "talk_time": "14h 10m", "policies": 41, "conversion": 19.8},
            {"name": "David Chen", "calls": 388, "talk_time": "12h 30m", "policies": 37, "conversion": 18.1},
            {"name": "Sarah Johnson", "calls": 401, "talk_time": "13h 12m", "policies": 35, "conversion": 17.5},
            {"name": "James Okafor", "calls": 360, "talk_time": "11h 02m", "policies": 33, "conversion": 17.0},
            {"name": "Priya Patel", "calls": 345, "talk_time": "10h 31m", "policies": 29, "conversion": 16.2},
            {"name": "Luis Romero", "calls": 322, "talk_time": "9h 48m", "policies": 26, "conversion": 15.1},
            {"name": "Aisha Bello", "calls": 298, "talk_time": "9h 05m", "policies": 24, "conversion": 14.6},
        ],
    }
