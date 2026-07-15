"""Sample data used in DEMO mode (when no TLDCRM credentials are configured)."""


def get_sample_dashboard(range_label="This Month"):
    return {
        "demo": True,
        "range_label": range_label,
        "kpis": {
            "policies_sold": 312,
            "billable_calls": 2480,
            "conversion_rate": 16.9,
            "avg_gtl_premium": 1562,
            "total_spend": 5460,
            "blended_cpa": 24.27,
        },
        "by_carrier": [
            {"label": "Aetna", "count": 87, "enrolled": 18},
            {"label": "UnitedHealthcare", "count": 75, "enrolled": 15},
            {"label": "Humana", "count": 59, "enrolled": 12},
            {"label": "Cigna", "count": 44, "enrolled": 9},
            {"label": "WellCare", "count": 28, "enrolled": 6},
            {"label": "Other", "count": 19, "enrolled": 3},
        ],
        "by_state": [
            {"state": "TX", "count": 42, "enrolled": 9,
             "carriers": [{"label": "UHC", "count": 18}, {"label": "Aetna", "count": 12}, {"label": "Humana", "count": 8}, {"label": "Cigna", "count": 4}],
             "agents": [{"name": "Okcuoglu, Kaan", "count": 10}, {"name": "Desir, G", "count": 8}, {"name": "Brown, Ernest", "count": 6}]},
            {"state": "FL", "count": 31, "enrolled": 7,
             "carriers": [{"label": "Aetna", "count": 14}, {"label": "UHC", "count": 10}, {"label": "WellCare", "count": 7}],
             "agents": [{"name": "Barros, Matheus", "count": 9}, {"name": "Chevelon, Ziea", "count": 6}]},
            {"state": "GA", "count": 18, "enrolled": 4,
             "carriers": [{"label": "Humana", "count": 9}, {"label": "UHC", "count": 6}, {"label": "Anthem", "count": 3}],
             "agents": [{"name": "Teheran, Eli", "count": 5}, {"name": "Desir, G", "count": 4}]},
            {"state": "OH", "count": 12, "enrolled": 2,
             "carriers": [{"label": "Anthem", "count": 7}, {"label": "Aetna", "count": 5}],
             "agents": [{"name": "Mckenzie, Michael", "count": 4}]},
            {"state": "NC", "count": 9, "enrolled": 2, "carriers": [{"label": "UHC", "count": 5}, {"label": "Cigna", "count": 4}], "agents": [{"name": "Desir, G", "count": 3}]},
            {"state": "PA", "count": 7, "enrolled": 1, "carriers": [{"label": "Aetna", "count": 4}, {"label": "UHC", "count": 3}], "agents": []},
            {"state": "AZ", "count": 5, "enrolled": 1, "carriers": [{"label": "Humana", "count": 3}], "agents": []},
            {"state": "MI", "count": 4, "enrolled": 0, "carriers": [{"label": "UHC", "count": 4}], "agents": []},
            {"state": "TN", "count": 3, "enrolled": 1, "carriers": [{"label": "Cigna", "count": 3}], "agents": []},
        ],
        "recent_sales": [
            {"date_sold": "Jun 24", "lead_id": 143634913, "agent": "Maria Alvarez", "agent_commission": 80.00, "enroller": "Carlos Ruiz", "fronter_commission": 30.00, "carrier": "Aetna"},
            {"date_sold": "Jun 24", "lead_id": 143634871, "agent": "David Chen", "agent_commission": 75.00, "enroller": "Tina Brooks", "fronter_commission": 28.00, "carrier": "UnitedHealthcare"},
            {"date_sold": "Jun 24", "lead_id": 143634802, "agent": "Sarah Johnson", "agent_commission": 60.00, "enroller": None, "fronter_commission": None, "carrier": "Guarantee Trust Life"},
            {"date_sold": "Jun 23", "lead_id": 143634399, "agent": "James Okafor", "agent_commission": 82.50, "enroller": "Marcus Lee", "fronter_commission": 30.00, "carrier": "Cigna"},
            {"date_sold": "Jun 23", "lead_id": 143634120, "agent": "Priya Patel", "agent_commission": 70.00, "enroller": "Carlos Ruiz", "fronter_commission": 25.00, "carrier": "WellCare"},
            {"date_sold": "Jun 23", "lead_id": 143633988, "agent": "Luis Romero", "agent_commission": 78.00, "enroller": "Tina Brooks", "fronter_commission": 30.00, "carrier": "Humana"},
        ],
        "agents": [
            {"name": "Maria Alvarez", "calls": 412, "talk_time": "14h 10m", "policies": 41, "conversion": 19.8, "cost": 754, "cpa": 18.40},
            {"name": "David Chen", "calls": 388, "talk_time": "12h 30m", "policies": 37, "conversion": 18.1, "cost": 779, "cpa": 21.05},
            {"name": "Sarah Johnson", "calls": 401, "talk_time": "13h 12m", "policies": 35, "conversion": 17.5, "cost": 851, "cpa": 24.30},
            {"name": "James Okafor", "calls": 360, "talk_time": "11h 02m", "policies": 33, "conversion": 17.0, "cost": 751, "cpa": 22.75},
            {"name": "Priya Patel", "calls": 345, "talk_time": "10h 31m", "policies": 29, "conversion": 16.2, "cost": 800, "cpa": 27.60},
            {"name": "Luis Romero", "calls": 322, "talk_time": "9h 48m", "policies": 26, "conversion": 15.1, "cost": 810, "cpa": 31.15},
            {"name": "Aisha Bello", "calls": 298, "talk_time": "9h 05m", "policies": 24, "conversion": 14.6, "cost": 715, "cpa": 29.80},
        ],
        "agent_totals": {"policies": 225, "cost": 5460, "cpa": 24.27},
        "enrollments": {
            "total": 29,
            "no_enroller": 27,
            "by_enroller": [
                {"fronter_id": "40067", "name": "Charles, Rony", "count": 7},
                {"fronter_id": "14847", "name": "Desir, G", "count": 5},
                {"fronter_id": "38784", "name": "Escoffery, Lashaunah", "count": 5},
                {"fronter_id": "42283", "name": "Chevelon, Ziea", "count": 4},
                {"fronter_id": "52081", "name": "Teheran, Eli", "count": 3},
                {"fronter_id": "51497", "name": "Lozano, Mario", "count": 2},
                {"fronter_id": "37669", "name": "Desormot, Jean", "count": 1},
                {"fronter_id": "43148", "name": "Gomez, Carlos", "count": 2},
            ],
        },
    }


def get_sample_board(range_label="Today"):
    """Placeholder Sales Board data shown in DEMO mode."""
    return {
        "demo": True,
        "range_label": range_label,
        "board": [
            {"name": "Okcuoglu, Kaan", "closed": 12, "enrolled": 3, "total": 15, "commission": 1050.00,
             "carriers": [{"label": "UHC", "count": 6}, {"label": "Aetna", "count": 4}, {"label": "Humana", "count": 2}]},
            {"name": "Desir, G", "closed": 9, "enrolled": 5, "total": 14, "commission": 870.00,
             "carriers": [{"label": "Aetna", "count": 5}, {"label": "UHC", "count": 4}]},
            {"name": "Brown, Ernest", "closed": 11, "enrolled": 0, "total": 11, "commission": 880.00,
             "carriers": [{"label": "Humana", "count": 6}, {"label": "Cigna", "count": 3}, {"label": "UHC", "count": 2}]},
            {"name": "Escoffery, Lashaunah", "closed": 0, "enrolled": 9, "total": 9, "commission": 270.00, "carriers": []},
            {"name": "Mckenzie, Michael", "closed": 7, "enrolled": 1, "total": 8, "commission": 590.00,
             "carriers": [{"label": "WellCare", "count": 4}, {"label": "Aetna", "count": 3}]},
            {"name": "Teheran, Eli", "closed": 0, "enrolled": 7, "total": 7, "commission": 210.00, "carriers": []},
            {"name": "Barros, Matheus", "closed": 6, "enrolled": 0, "total": 6, "commission": 480.00,
             "carriers": [{"label": "UHC", "count": 3}, {"label": "Humana", "count": 3}]},
            {"name": "Chevelon, Ziea", "closed": 2, "enrolled": 4, "total": 6, "commission": 280.00,
             "carriers": [{"label": "Aetna", "count": 2}]},
        ],
    }
