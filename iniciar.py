import subprocess, sys, os
os.chdir(r"C:\Users\fabio\prospeccion-pskloud")
print("\n  PSKloud Prospector v2.3\n  http://localhost:8501\n")
subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"])
