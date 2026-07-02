import os

templates_dir = r"c:\Users\silve\Desktop\MEMOIRE\AOCEDA\templates"

for filename in os.listdir(templates_dir):
    if not filename.endswith(".html"):
        continue
        
    file_path = os.path.join(templates_dir, filename)
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Check if already has verbatim or doesn't have the script tag
    if "{% verbatim %}" in content:
        print(f"Skipping {filename} - already contains verbatim tags.")
        continue
        
    script_start = '<script type="text/babel">'
    script_end = '</script>'
    
    start_idx = content.find(script_start)
    end_idx = content.find(script_end, start_idx)
    
    if start_idx == -1 or end_idx == -1:
        print(f"Skipping {filename} - script tags not found.")
        continue
        
    print(f"Wrapping script block in {filename}...")
    
    # We want to place verbatim tags around the script tag block
    new_content = (
        content[:start_idx] + 
        "{% verbatim %}\n" + 
        content[start_idx:end_idx + len(script_end)] + 
        "\n{% endverbatim %}" + 
        content[end_idx + len(script_end):]
    )
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)

print("All templates processed successfully!")
