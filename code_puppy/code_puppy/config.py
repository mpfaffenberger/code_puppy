@@ -7,8 +7,14 @@
-CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".code_puppy")
-CONFIG_FILE = os.path.join(CONFIG_DIR, "puppy.cfg")
+CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".code_puppy")
+CONFIG_FILE = os.path.join(CONFIG_DIR, "puppy.cfg")
+
+# Supported prompt themes
+PROMPT_THEMES = ["puppy", "tron", "star_wars", "star_trek", "sci_fi"]

@@ -11,7 +17,9 @@
-REQUIRED_KEYS = ["puppy_name", "owner_name"]
+REQUIRED_KEYS = ["agent_name", "owner_name", "agent_theme"]

@@ -30,7 +38,22 @@
-    for key in REQUIRED_KEYS:
-        if not config[DEFAULT_SECTION].get(key):
-            missing.append(key)
-    if missing:
-        print(" Let's get your Puppy ready!")
-        for key in missing:
-            if key == "puppy_name":
-                val = input("What should we name the puppy? ").strip()
-            elif key == "owner_name":
-                val = input(
-                    "What's your name (so Code Puppy knows its master)? "
-                ).strip()
-            else:
-                val = input(f"Enter {key}: ").strip()
-            config[DEFAULT_SECTION][key] = val
-        with open(CONFIG_FILE, "w") as f:
-            config.write(f)
+    for key in REQUIRED_KEYS:
+        if not config[DEFAULT_SECTION].get(key):
+            missing.append(key)
+    if missing:
+        print("Let's get your agent ready!")
+        for key in missing:
+            if key == "agent_name":
+                val = input("What is your agent's name? (e.g., clu, Puppy, R2D2): ").strip()
+            elif key == "owner_name":
+                val = input("What's your name (so the agent knows its user)? ").strip()
+            elif key == "agent_theme":
+                print("Choose a prompt theme:")
+                for idx, theme in enumerate(PROMPT_THEMES):
+                    print(f"  {idx+1}. {theme}")
+                while True:
+                    sel = input("Theme (number or name): ").strip()
+                    if sel.isdigit() and 1 <= int(sel) <= len(PROMPT_THEMES):
+                        val = PROMPT_THEMES[int(sel)-1]
+                        break
+                    elif sel in PROMPT_THEMES:
+                        val = sel
+                        break
+                    else:
+                        print("Invalid theme. Please select by number or name.")
+            else:
+                val = input(f"Enter {key}: ").strip()
+            config[DEFAULT_SECTION][key] = val
+        with open(CONFIG_FILE, "w") as f:
+            config.write(f)
@@ -55,8 +77,34 @@
-def get_puppy_name():
-    return get_value("puppy_name") or "Puppy"
-
-def get_owner_name():
-    return get_value("owner_name") or "Master"
+
+def get_agent_name():
+    return get_value("agent_name") or "Agent"
+
+def get_owner_name():
+    return get_value("owner_name") or "User"
+
+def get_agent_theme():
+    return get_value("agent_theme") or "puppy"
