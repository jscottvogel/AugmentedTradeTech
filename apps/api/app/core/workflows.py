DEFAULT_WORKFLOW_CONFIG = {
    "hvac": {
        "steps": [
            {
                "key": "arrive_on_site",
                "name": "Arrive on Site",
                "type": "photo",
                "required": True,
                "description": "Photo: unit exterior (before). Confirm reported symptoms. Note access issues.",
                "config": {"photo_required": True}
            },
            {
                "key": "equipment_id",
                "name": "Equipment Identification",
                "type": "photo",
                "required": True,
                "description": "Photo: nameplate -> AI extracts make, model, serial, tonnage, age. Auto-populates job record.",
                "config": {"photo_required": True}
            },
            {
                "key": "safety_power_check",
                "name": "Safety & Power Check",
                "type": "checklist",
                "required": True,
                "description": "Confirm disconnect status. Photo: electrical panel. Note any hazards.",
                "config": {
                    "items": [
                        "Disconnect is OFF/Safe",
                        "No immediate hazards present",
                        "Lockout/Tagout applied if required"
                    ]
                }
            },
            {
                "key": "filter_airflow",
                "name": "Filter & Airflow",
                "type": "multi_choice",
                "required": True,
                "description": "Photo: filter condition. Log filter size and MERV rating. AI flags if severely restricted.",
                "config": {
                    "options": [
                        "Clean / Good condition",
                        "Slightly dirty / Monitor",
                        "Restricted / Needs replacement",
                        "Missing"
                    ]
                }
            },
            {
                "key": "duct_inspection",
                "name": "Duct Inspection",
                "type": "photo",
                "required": False,
                "description": "Photo: visible duct sections. Note leaks, damage, or insulation issues. AI analyzes photo.",
                "config": {"photo_required": False}
            },
            {
                "key": "refrigerant_pressures",
                "name": "Refrigerant & Pressures",
                "type": "numeric",
                "required": True,
                "description": "Log suction pressure, discharge pressure. AI calculates superheat/subcooling and flags anomalies.",
                "config": {
                    "unit": "PSI",
                    "min_value": 0.0,
                    "max_value": 800.0
                }
            },
            {
                "key": "temperature_readings",
                "name": "Temperature Readings",
                "type": "numeric",
                "required": True,
                "description": "Log supply air temp, return air temp. AI calculates delta-T and flags if out of range.",
                "config": {
                    "unit": "°F",
                    "min_value": -40.0,
                    "max_value": 150.0
                }
            },
            {
                "key": "electrical_components",
                "name": "Electrical & Components",
                "type": "photo",
                "required": False,
                "description": "Photo: capacitor, contactor, wiring. Log voltage and amp readings. AI identifies visible wear or failure.",
                "config": {"photo_required": False}
            },
            {
                "key": "ai_diagnosis",
                "name": "AI Diagnosis",
                "type": "ai_trigger",
                "required": True,
                "description": "AI synthesizes all readings and photos. Presents likely root causes with confidence levels and recommended repair steps.",
                "config": {"trigger_analysis": True}
            },
            {
                "key": "diagnosis_repair",
                "name": "Diagnosis & Repair",
                "type": "text",
                "required": True,
                "description": "Log parts used. Voice or typed work performed notes. AI drafts job summary.",
                "config": {"placeholder": "Describe repairs performed..."}
            },
            {
                "key": "system_verification",
                "name": "System Verification",
                "type": "checklist",
                "required": True,
                "description": "Post-repair pressure and temp readings. Photo: unit after. Confirm system operating normally.",
                "config": {
                    "items": [
                        "Unit cycles on and off properly",
                        "Thermostat responds normally",
                        "Working area left clean"
                    ]
                }
            },
            {
                "key": "wrap_up",
                "name": "Wrap Up",
                "type": "voice",
                "required": True,
                "description": "Customer signature. Invoice review. Payment collection.",
                "config": {"memo_required": False}
            }
        ]
    },
    "garage_door": {
        "steps": [
            {
                "key": "arrive_on_site",
                "name": "Arrive on Site",
                "type": "photo",
                "required": True,
                "description": "Photo: door exterior (before). Confirm reported symptoms.",
                "config": {"photo_required": True}
            },
            {
                "key": "door_identification",
                "name": "Door Identification",
                "type": "multi_choice",
                "required": True,
                "description": "Note door type (sectional/roll-up/carriage), brand, size, age.",
                "config": {
                    "options": [
                        "Sectional Steel",
                        "Sectional Wood",
                        "Roll-up / Commercial",
                        "Carriage House",
                        "One-Piece Tilt"
                    ]
                }
            },
            {
                "key": "safety_inspection",
                "name": "Safety Inspection",
                "type": "checklist",
                "required": True,
                "description": "Auto-reverse test result. Sensor alignment check. Photo: sensors. Manual operation test.",
                "config": {
                    "items": [
                        "Auto-reverse test passed",
                        "Photo-eye sensors aligned",
                        "Manual release operates freely"
                    ]
                }
            },
            {
                "key": "spring_system",
                "name": "Spring System",
                "type": "photo",
                "required": True,
                "description": "Photo: spring condition. Note spring type (torsion/extension). Log winding turns. AI flags wear, imbalance, or failure risk.",
                "config": {"photo_required": True}
            },
            {
                "key": "cable_drum_check",
                "name": "Cable & Drum Check",
                "type": "checklist",
                "required": True,
                "description": "Photo: cables and drums. Note fraying, slack, or misalignment.",
                "config": {
                    "items": [
                        "Cables free of visible fraying",
                        "Drums secure and aligned",
                        "Cable tension is equal on both sides"
                    ]
                }
            },
            {
                "key": "track_hardware",
                "name": "Track & Hardware",
                "type": "checklist",
                "required": True,
                "description": "Photo: tracks, rollers, hinges, brackets. Note bent tracks or worn rollers.",
                "config": {
                    "items": [
                        "Tracks are aligned and unbent",
                        "Rollers turn freely without binding",
                        "Hinges and brackets are secure"
                    ]
                }
            },
            {
                "key": "opener_inspection",
                "name": "Opener Inspection",
                "type": "text",
                "required": False,
                "description": "Note brand, model, age. Log force and limit settings. Photo: drive mechanism. AI flags if settings are out of spec.",
                "config": {"placeholder": "Enter opener status/force settings..."}
            },
            {
                "key": "lubrication",
                "name": "Lubrication",
                "type": "checklist",
                "required": True,
                "description": "Confirm components lubricated. Note products used.",
                "config": {
                    "items": [
                        "Springs lubricated",
                        "Tracks and rollers lubricated",
                        "Hinges lubricated"
                    ]
                }
            },
            {
                "key": "balance_test",
                "name": "Balance Test",
                "type": "multi_choice",
                "required": True,
                "description": "Manual balance test result. AI provides guidance if door fails balance.",
                "config": {
                    "options": [
                        "Perfect balance",
                        "Slightly heavy / light tension",
                        "Severely out of balance / dangerous"
                    ]
                }
            },
            {
                "key": "ai_diagnosis",
                "name": "AI Diagnosis",
                "type": "ai_trigger",
                "required": True,
                "description": "AI synthesizes all inspection data. Presents likely issues with repair recommendations.",
                "config": {"trigger_analysis": True}
            },
            {
                "key": "diagnosis_repair",
                "name": "Diagnosis & Repair",
                "type": "text",
                "required": True,
                "description": "Log parts used. Work performed notes. AI drafts job summary.",
                "config": {"placeholder": "Describe repairs performed..."}
            },
            {
                "key": "wrap_up",
                "name": "Wrap Up",
                "type": "photo",
                "required": True,
                "description": "Verify door operation. Photo: after. Customer signature and payment.",
                "config": {"photo_required": True}
            }
        ]
    }
}
