import os
import re
from pathlib import Path

# Load test IDs and subject IDs
known_test_ids = [
    "luchevaya_test_blank",
    "luchevaya_razdel_2",
    "luchevaya_razdel_3",
    "luchevaya_razdel_6",
    "farm_final",
    "farm_peptides",
    "farm_steroids",
    "oziz_1_200",
    "oziz_200_400",
    "oziz_400+",
    "oziz_module_2",
    "voprosi2",
    "voprosi3"
]

# A Cyrillic slug can easily be 30-40 bytes
sample_subjects = [
    "luchevaya_diagnostika",
    "лучевая_диагностика",
    "основы_лучевой_диагностики",
    "фармакология",
    "общественное_здоровье_и_здравоохранение"
]

py_files = list(Path("quiz_bot").rglob("*.py"))

cb_regex = re.compile(r'callback_data\s*=\s*(f?["\'].*?["\'])')

print("=== Analyzing callback_data across all quiz_bot files ===")
for p in py_files:
    text = p.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), 1):
        for m in cb_regex.finditer(line):
            raw = m.group(1)
            # Evaluate potential lengths
            max_len = 0
            worst_case = ""
            if raw.startswith("f"):
                template = raw[2:-1]
                # Try substituting
                for s in sample_subjects:
                    for t in known_test_ids:
                        sub = (template
                               .replace("{subject_id}", s)
                               .replace("{test_id}", t)
                               .replace("{attempt_id}", "att_1234567890")
                               .replace("{index}", "100")
                               .replace("{page}", "10")
                               .replace("{pos}", "10")
                               .replace("{question_index}", "100")
                               .replace("{access}", "admin_only")
                               .replace("{type}", "admin_only")
                               .replace("{prefix}", "find_results_page")
                               )
                        l_bytes = len(sub.encode("utf-8"))
                        if l_bytes > max_len:
                            max_len = l_bytes
                            worst_case = sub
            else:
                static_val = raw[1:-1]
                max_len = len(static_val.encode("utf-8"))
                worst_case = static_val

            if max_len > 60:
                print(f"[{'DANGER >64' if max_len > 64 else 'WARNING >60'}] {p.name}:{i}")
                print(f"   raw: {raw}")
                print(f"   len: {max_len} bytes")
                print(f"   worst: {worst_case}\n")
