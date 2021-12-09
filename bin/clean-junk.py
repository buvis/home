import os


def clean_folder(path):
    for filename in os.listdir(path):
        os.remove(os.path.join(path, filename))

clean_folder(r"C:\Users\Public\Desktop")
clean_folder(r"C:\Users\tbouska\OneDrive - Automatic Data Processing Inc\Desktop")

# Unwanted startup items
startup_folder = r"C:\Users\tbouska\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup"
unwanted_files = ["Map.exe", "EUCnwvpn.exe", "My ADP Portal.url"]

for filename in unwanted_files:
    full_path = os.path.join(startup_folder, filename)

    if os.path.isfile(full_path):
        os.remove(full_path)
