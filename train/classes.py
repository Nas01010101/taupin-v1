"""Class definitions shared by the data scripts and training.

Each class maps to one or more iNaturalist queries. `term_id=1` is the iNaturalist "Life Stage"
annotation; value 2 is Adult, 6 is Larva. `relax` allows needs_id observations with at least one
agreeing identification and no disagreement, used where research-grade data is scarce.
"""

LARVA = {"term_id": 1, "term_value_id": 6}
ADULT = {"term_id": 1, "term_value_id": 2}

# id, display name, pest flag, list of (iNat taxon ids, extra params, cap, relax)
CLASSES = [
    ("wireworm", "Wireworm (click beetle larva)", True,
     [("53248", LARVA, 1000, True)]),
    ("click_beetle", "Click beetle (adult)", True,
     [("53248", ADULT, 700, False)]),
    ("corn_rootworm", "Corn rootworm beetle (adult)", True,
     [("218294,200013", {}, 1000, True)]),
    ("white_grub", "White grub (scarab larva)", True,
     [("48201", LARVA, 1000, True)]),
    ("ground_beetle", "Ground beetle (beneficial)", False,
     [("49567", ADULT, 700, False)]),
    ("millipede", "Millipede (not an insect)", False,
     [("47735", {}, 700, False)]),
    ("earthworm", "Earthworm (beneficial)", False,
     [("69758", {}, 700, False)]),
    ("other", "Other soil animal or object", False, [
        ("49556", {}, 90, False),            # Chilopoda, centipedes
        ("48147", {}, 90, False),            # Isopoda, woodlice
        ("53816", LARVA, 200, True),         # Tenebrionidae larvae, false wireworms
        ("51225", LARVA, 200, True),         # Tipulidae larvae, leatherjackets
        ("48670", LARVA, 120, False),        # Noctuidae larvae, cutworms
        ("47951", {}, 70, False),            # Staphylinidae, rove beetles
        ("47336", {}, 70, False),            # Formicidae, ants
        ("47118", {}, 70, False),            # Araneae, spiders
        ("47114", {}, 60, False),            # Gastropoda (slugs, snails)
        ("47208", {**LARVA, "without_taxon_id": "53248,48201,49567"}, 80, False),  # other beetle larvae
        ("47157", LARVA, 60, False),         # Lepidoptera larvae
        ("47126", {}, 60, False),            # Plantae, non-animal photos
        ("47170", {}, 40, False),            # Fungi
    ]),
]

CLASS_IDS = [c[0] for c in CLASSES]
