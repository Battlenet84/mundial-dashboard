import subprocess
import sys


def main() -> None:
    raise SystemExit(
        subprocess.call([sys.executable, "-m", "streamlit", "run", "app/dashboard/streamlit_app.py"])
    )


if __name__ == "__main__":
    main()

