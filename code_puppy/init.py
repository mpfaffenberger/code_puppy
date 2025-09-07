# code_puppy init command creates a valid YAML file

import yaml

def run_init():
    print("🐶 Let's make your Puppy Rules Spec!")
    theme = input("1. Theme (light/dark) [dark]: ") or "dark"
    accent = input("2. Accent color (CSS name or hex) [teal]: ") or "teal"
    naming = input("3. Naming convention (snake_case/camelCase) [snake_case]: ") or "snake_case"
    config = {
        "theme": theme,
        "accent-color": accent,
        "naming-convention": naming
    }
    with open(".code_puppy_rules.yml", "w") as f:
        yaml.dump(config, f)
    print(".code_puppy_rules.yml has been created!")
