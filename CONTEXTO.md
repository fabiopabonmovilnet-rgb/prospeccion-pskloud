# =============================================================================
# CONTEXTO: PSKloud Prospector - Sistema de Prospección B2B v2.3
# =============================================================================
# COPIA TODO ESTE ARCHIVO EN TU PRIMER MENSAJE AL INICIAR NUEVA SESIÓN
# =============================================================================

## ESTADO ACTUAL: v2.3 FUNCIONAL — 5 países, ~152 empresas

### ✅ LO QUE YA FUNCIONA:
1. **Hunter.io API** — Busca contactos reales por dominio (plan free: 25 búsquedas/mes)
2. **152 empresas reales** en 5 países (CR, SV, PA, HN, CO)
3. **1 contacto por empresa** (el más senior)
4. **Exclusión con motivos** — Leads excluidos nunca reaparecen, guarda motivo + fecha
5. **Exportación CSV/Excel** de resultados
6. **Envío masivo SMTP vía SendGrid API** — 100 correos/día free
7. **Lusha API** — Teléfonos directos + datos de empresa + enriquecimiento por email
8. **Scrapers multi-fuente** en paralelo:
   - Páginas Amarillas (SV, CO, PA)
   - Yelu.cr (Costa Rica)
   - Infoguía Costa Rica
   - Lusha Company API
   - Lusha People API (por nombre o email)
   - Sitio web corporativo
9. **Pipeline de Ventas** — 6 etapas persistente en JSON
10. **UI con branding PSKloud** (rojo #CC0000)
11. **Ejecutable de escritorio** (.exe + .bat)
12. **CONTEXTO.md trackeado en GitHub**

### 📋 DATOS DE CONFIGURACIÓN:
- **Hunter API Key:** `f41f5e017f72032cdb59f1f1591dbb24e0600c9a`
- **Lusha API Key:** `(en secrets.toml local)`
- **SendGrid API Key:** `(en secrets.toml local)`
- **Remitente verificado SendGrid:** `pskloud.fpabon@gmail.com`
- **Hunter cuenta:** fpabon@premium-soft.com (Plan Free)
- **GitHub:** https://github.com/fabiopabonmovilnet-rgb/prospeccion-pskloud
- **Código local:** C:\Users\fabio\prospeccion-pskloud\app.py
- **Archivo secrets:** C:\Users\fabio\prospeccion-pskloud\.streamlit\secrets.toml (gitignored)

### 🏗️ ARCHIVOS DEL PROYECTO:
```
C:\Users\fabio\prospeccion-pskloud\
├── .streamlit/
│   ├── config.toml              # Tema PSKloud (rojo #CC0000)
│   ├── secrets.toml             # API Keys + SMTP (en .gitignore)
│   └── secrets.toml.example     # Template de ejemplo
├── app.py                       # Código principal (Streamlit) ~1970 líneas
├── enrichment.py                # Motor de enriquecimiento (scrapers multi-fuente)
├── CONTEXTO.md                  # ESTE ARCHIVO (trackeado en GitHub)
├── README.md                    # Documentación
├── requirements.txt             # Dependencias
├── .gitignore                   # secrets.toml, pipeline_estado.json, *.xlsx
├── lanzador.cs                  # Código fuente del .exe (C#)
├── leads_excluidos.json         # Persistencia de exclusiones (dict con motivos)
├── pipeline_estado.json         # Persistencia del pipeline (gitignored)
└── plantilla_personalizada.json # Plantilla de correo personalizada (gitignored)
```

### 📊 EMPRESAS POR PAÍS:
- **Costa Rica (~35):** Kambda, Siftia, Gorilla Logic, FusionHit, Banco Nacional, BCR, Dos Pinos, FIFCO + varias
- **El Salvador (~30):** Softcorp, Super Selectos, Siman, Banco Cuscatlán, Grupo Q, Holcim, Nestlé + nuevas
- **Panamá (~26):** DXC, Banco General, Súper 99, Copa Airlines, Grupo Melo, Cable Onda, Nestlé PA + nuevas
- **Honduras (~24):** Grupo Intellect, Banco Atlántida, Ficohsa, Grupo Karims, CENOSA, Dinant + nuevas
- **Colombia (~37):** Sofka, Globant, Bancolombia, Rappi, Mercado Libre, Avianca, Alpina + nuevas

### 🔧 EJECUCIÓN:
- **Doble clic:** `PSKloud Prospector.exe` en el Escritorio
- **Alternativa:** `streamlit run app.py` desde `C:\Users\fabio\prospeccion-pskloud`

### 🐛 ÚLTIMO BUG CORREGIDO:
- `from_addr` en envío SendGrid usaba `"apikey"` en vez de `"pskloud.fpabon@gmail.com"` por error en `st.secrets.get()` — corregido con valor directo

### 📝 PENDIENTES:
- [ ] Deploy a Streamlit Cloud con persistencia de datos
- [ ] Dashboard de métricas de campaña
- [ ] Expandir a Guatemala, Nicaragua

### 🔄 PARA CONTINUAR:
Copia TODO el contenido de CONTEXTO.md (este archivo) en tu primer mensaje de la nueva sesión.

Archivo visible en GitHub:
https://github.com/fabiopabonmovilnet-rgb/prospeccion-pskloud/blob/main/CONTEXTO.md
