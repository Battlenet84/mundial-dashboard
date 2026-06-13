# Deploy en GitHub + Streamlit Community Cloud

Esta carpeta está preparada para subir a GitHub y abrir el dashboard desde cualquier lugar, sin depender de que la computadora local esté prendida.

## Qué incluye

- `streamlit_app.py`: entrypoint raíz para Streamlit Cloud.
- `app/dashboard/betting_value_dashboard.py`: dashboard principal.
- `data/mundial.db`: base SQLite liviana para el dashboard, sin raw payload pesado.
- `requirements.txt`: dependencias necesarias para instalar en Streamlit Cloud.
- `.streamlit/config.toml`: configuración visual básica.
- `.streamlit/secrets.example.toml`: ejemplo opcional para contraseña.

## Qué NO incluye

- `.env` ni claves privadas.
- `data/raw/` pesado.
- `data/processed/` pesado.
- `__pycache__` ni archivos temporales.

## Probar localmente

```powershell
cd C:\Users\saieg\OneDrive\Desktop\mundial
pip install -r requirements.txt
streamlit run streamlit_app.py
```

También podés correr directo:

```powershell
streamlit run app/dashboard/betting_value_dashboard.py
```

## Subir a GitHub

Desde la carpeta del repo:

```powershell
git init
git add .
git commit -m "Prepare Streamlit dashboard deploy"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/mundial-dashboard.git
git push -u origin main
```

## Deploy en Streamlit Community Cloud

1. Entrar a Streamlit Community Cloud.
2. Crear una app nueva.
3. Elegir el repo de GitHub.
4. Branch: `main`.
5. Main file path: `streamlit_app.py`.
6. Deploy.

## Contraseña opcional

Por defecto la app queda pública. Si querés poner password, en Streamlit Cloud agregá este secret:

```toml
APP_PASSWORD = "tu-password"
```

No subas `.streamlit/secrets.toml` a GitHub.

## Actualizar datos

Esta versión usa `data/mundial.db` incluido en el repo. Si recalculás EV/localmente y querés actualizar la app pública:

1. Reemplazá `data/mundial.db` por la nueva base liviana.
2. Corré localmente:

```powershell
python -m py_compile streamlit_app.py app/dashboard/betting_value_dashboard.py app/betting/odds_driven.py
streamlit run streamlit_app.py
```

3. Subí cambios:

```powershell
git add data/mundial.db app/dashboard/betting_value_dashboard.py app/betting/odds_driven.py
git commit -m "Update dashboard data"
git push
```

Streamlit Cloud redeploya automáticamente después del push.
