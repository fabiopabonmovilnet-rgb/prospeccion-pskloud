# =============================================================================
# CONTEXTO: PSKloud Prospector - Sistema de Prospección B2B
# =============================================================================
# ARCHIVO PARA CONTINUAR EL PROYECTO - Copiar/pegar al iniciar nueva sesión
# =============================================================================

## ESTADO ACTUAL: v2.0 FUNCIONAL

### ✅ LO QUE YA FUNCIONA:
1. **Hunter.io API integrada** — Busca contactos reales en empresas de CR y SV
2. **50+ empresas reales** con dominios verificados en la base de datos
3. **1 contacto por empresa** — El más senior (CEO > Director > Gerente)
4. **Sistema de exclusión** — Leads marcados como vistos no vuelven a aparecer
5. **Exportación CSV/Excel** — Descargar base de datos
6. **Plantilla de correo PSKloud** — Con variables dinámicas
7. **Envío SMTP real** — Configurable (Gmail, Outlook, etc.)
8. **API Key persistente** — Se guarda en `.streamlit/secrets.toml`, no hay que pegarla cada vez
9. **Enriquecimiento con teléfonos** — Busca en Páginas Amarillas SV, Yelu.cr, Infoguía CR y sitios web
10. **UI mejorada** — Branding PSKloud, tarjetas, métricas visuales

### 📋 DATOS DE CONFIGURACIÓN:
- **API Key Hunter.io:** `f41f5e017f72032cdb59f1f1591dbb24e0600c9a`
- **Cuenta:** fpabon@premium-soft.com (Plan Free: 50 búsquedas/mes)
- **Repositorio GitHub:** https://github.com/fabiopabonmovilnet-rgb/prospeccion-pskloud
- **Localización código:** C:\Users\fabio\prospeccion-pskloud\app.py
- **Archivo de exclusiones:** C:\Users\fabio\prospeccion-pskloud\leads_excluidos.json

### 🏗️ ARCHIVOS DEL PROYECTO:
```
C:\Users\fabio\prospeccion-pskloud\
├── .streamlit/
│   ├── config.toml             # Tema PSKloud (rojo #CC0000)
│   └── secrets.toml            # API Key Hunter + SMTP (en .gitignore)
├── app.py                      # Código principal (Streamlit) ~1650 líneas
├── enrichment.py               # Motor de enriquecimiento (scrapers multi-fuente)
├── requirements.txt            # Dependencias
├── leads_excluidos.json        # Persistencia de leads excluidos
├── pipeline_estado.json        # Persistencia del pipeline de ventas
├── lanzador.cs                 # Código fuente del .exe (C#)
├── CONTEXTO.md                 # ESTE ARCHIVO
├── README.md                   # Documentación
└── .gitignore                  # Archivos ignorados
```

### 🎯 FUNCIONALIDADES POR COMPONENTE:

**Componente 1: Búsqueda de Leads**
- Dropdown: Costa Rica / El Salvador
- Dropdown: Canales/Distribuidores / Clientes Finales
- Dropdown: Sector (se adapta al target seleccionado)
- Slider: Contactos por empresa (3-10)
- Checkboxes para excluir leads vistos
- Persistencia de exclusiones en JSON

**Componente 2: Configurador de Campañas**
- Plantilla PSKloud por defecto
- Variables: {{nombre}}, {{empresa}}, {{pais}}, {{cargo}}, {{email}}
- Vista previa en tiempo real

**Componente 3: Envío Masivo SMTP**
- Configuración SMTP (servidor, puerto, email, contraseña)
- Envío real con smtplib
- Barra de progreso y logs

### 🐛 BUGS CORREGIDOS:
1. Parsing de respuesta Hunter.io (nivel "data" anidado)
2. Dominios de El Salvador corregidos (muchos no existían)
3. Filtros ahora son dropdowns preconfigurados para PSKloud
4. Solo 1 contacto por empresa (evitar repetición)

### 📊 EMPRESAS EN LA BASE DE DATOS:
**Costa Rica (~35 empresas):**
- Tecnología: Kambda, Siftia, Gorilla Logic, FusionHit, Infosgroup, etc.
- Retail: Grupo Palí, AutoMercado, Farmacia Fischel, Vindi
- Finanzas: Banco Nacional, BCR, BAC, Grupo Mutual, INS
- Salud: Clínica Bíblica, Hospital CIMA, Laboratorios Lahey
- Turismo: Hotel Marriott, Grupo Tilajari
- Manufactura: Dos Pinos, FIFCO, Cementos Portland

**El Salvador (~20 empresas):**
- Tecnología: Softcorp, GInIEm, Intecno Solutions
- Retail: Super Selectos, Siman, La Curacao
- Finanzas: Banco Cuscatlán, Banco Agrícola, Davivienda
- Telecomunicaciones: Tigo, Claro, Telefónica
- Manufactura: Heineken, Pilsener, Cementos

**Panamá (~15 empresas):**
- Tecnología: DXC Technology, Yuxi Global, Waked Technology
- Finanzas: Banco General, BAC Panama, Towerbank, Scotiabank
- Retail: Súper 99, Rey, El Machetazo
- Telecomunicaciones: Claro, Digicel
- Turismo/Logística: Copa Airlines, Panama Ports
- Manufactura: Cervecería Nacional

**Honduras (~12 empresas):**
- Tecnología: Grupo Intellect, Datasys HN
- Finanzas: Banco Atlántida, Ficohsa, BAC, Lafise
- Retail: La Colonia, Despensa Familiar
- Telecomunicaciones: Tigo, Claro
- Manufactura: Kimberly Clark, Cementos Argos

**Colombia (~22 empresas):**
- Tecnología: Sofka, Globant, Periferia IT, Mismo, Intergrupo
- Finanzas: Bancolombia, Davivienda, Grupo Sura, BBVA
- Retail: Éxito, Falabella, Homecenter, Alkosto
- Telecomunicaciones: Tigo, Movistar, Claro
- Energía: Ecopetrol, EPM, ISA
- Manufactura: Grupo Nutresa, Postobón, Cementos Argos

### 🔧 PARA EJECUTAR:
```powershell
cd C:\Users\fabio\prospeccion-pskloud
streamlit run app.py
```
Abrir: http://localhost:8501

**Doble clic (recomendado):**
- `C:\Users\fabio\Desktop\PSKloud Prospector.exe` — Ejecutable real (Windows)
- `C:\Users\fabio\Desktop\PSKloud Prospector.bat` — Alternativa (script batch)

Ambos abren automáticamente el navegador en http://localhost:8501

### 📦 INSTALACIÓN DESDE CERO (si cambias de PC):
```powershell
cd C:\Users\fabio\prospeccion-pskloud
pip install -r requirements.txt
# Crear secrets.toml con la API key (ver NOTAS IMPORTANTES)
```

### 🚀 PARA SUBIR CAMBIOS A GITHUB:
```powershell
cd C:\Users\fabio\prospeccion-pskloud
git add -A
git commit -m "descripcion del cambio"
git push
```

### 📝 PENDIENTES / PRÓXIMOS PASOS:
- [x] Deploy a Streamlit Cloud — Configurado (.streamlit/config.toml + secrets)
- [x] API Key persistente en secrets.toml
- [x] Módulo de enriquecimiento con teléfonos (Páginas Amarillas, Yelu, Infoguía, webs)
- [x] UI mejorada con branding PSKloud
- [x] Pipeline de ventas (etapas: Nuevo → Email → LinkedIn → Llamada → Cliente/Perdido)
- [x] Pipeline persistente en pipeline_estado.json
- [x] Componente 4: Vista de pipeline + notas + filtros
- [ ] Agregar más empresas a la base de datos
- [ ] Integrar scraping de directorios públicos adicionales
- [ ] Sistema de deduplicación entre sesiones
- [ ] Dashboard de métricas de campaña
- [ ] Scraping de LinkedIn (bajo investigación — TOS restrictivo)
- [ ] Deploy multi-usuario (Streamlit Cloud compartido)
- [ ] Expandir a más países (Guatemala, Panamá, etc.)

### 💡 NOTAS IMPORTANTES:
1. **Hunter.io NO provee teléfonos** — Solo emails y LinkedIn personal
2. **Créditos limitados** — 50 búsquedas/mes en plan gratuito
3. **Los leads excluidos se guardan** en leads_excluidos.json (persiste LOCALMENTE). En Streamlit Cloud la persistencia es por sesión.
4. **API Key Hunter** se guarda en `.streamlit/secrets.toml` — ya no hay que pegarla cada vez. Si cambias de PC, crea ese archivo.
5. **Enriquecimiento de teléfonos** — Botón "Buscar Teléfonos" después de obtener leads. Scrapea:
   - Páginas Amarillas (SV, CO, PA)
   - Yelu.cr (Costa Rica)
   - Infoguía Costa Rica
   - Sitio web corporativo (scraping directo)
   - ⚠️ Los teléfonos son de la EMPRESA (recepcionista), no directos del gerente
   - Honduras solo usa scraping web (no tiene Páginas Amarillas)
6. **Pipeline de Ventas** — Componente 4, persistente en pipeline_estado.json
7. **5 países soportados:** Costa Rica, El Salvador, Panamá, Honduras, Colombia
8. **Ejecutable de escritorio (.exe):** `C:\Users\fabio\Desktop\PSKloud Prospector.exe`
9. **Ejecutable de escritorio (.bat):** `C:\Users\fabio\Desktop\PSKloud Prospector.bat`
10. **CONTEXTO.md está en .gitignore** — No se sube al repo

### 🔄 CÓMO CONTINUAR:
1. Leer este archivo CONTEXTO.md
2. Ejecutar — doble clic en `PSKloud Prospector.exe` (Escritorio) o `streamlit run app.py`
3. Probar funcionalidad
4. Implementar mejoras pendientes
5. Subir cambios a GitHub

### 📞 CONTACTO:
- Usuario: Fabio Pabon
- Empresa: PSKloud (premium-soft.com)
- GitHub: fabiopabonmovilnet-rgb

# =============================================================================
# FIN DEL CONTEXTO - COPIAR TODO LO ANTERIOR PARA CONTINUAR
# =============================================================================
