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

### 📋 DATOS DE CONFIGURACIÓN:
- **API Key Hunter.io:** `f41f5e017f72032cdb59f1f1591dbb24e0600c9a`
- **Cuenta:** fpabon@premium-soft.com (Plan Free: 50 búsquedas/mes)
- **Repositorio GitHub:** https://github.com/fabiopabonmovilnet-rgb/prospeccion-pskloud
- **Localización código:** C:\Users\fabio\prospeccion-pskloud\app.py
- **Archivo de exclusiones:** C:\Users\fabio\prospeccion-pskloud\leads_excluidos.json

### 🏗️ ARCHIVOS DEL PROYECTO:
```
C:\Users\fabio\prospeccion-pskloud\
├── app.py                    # Código principal (Streamlit)
├── requirements.txt          # Dependencias: streamlit, pandas, openpyxl, requests
├── leads_excluidos.json      # Persistencia de leads excluidos
├── CONTEXTO.md               # ESTE ARCHIVO
├── README.md                 # Documentación
└── .gitignore                # Archivos ignorados
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

### 📊 EMPREAS EN LA BASE DE DATOS:
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

### 🔧 PARA EJECUTAR:
```powershell
cd C:\Users\fabio\prospeccion-pskloud
streamlit run app.py
```
Abrir: http://localhost:8501

### 🚀 PARA SUBIR CAMBIOS A GITHUB:
```powershell
cd C:\Users\fabio\prospeccion-pskloud
git add -A
git commit -m "descripcion del cambio"
git push
```

### 📝 PENDIENTES / PRÓXIMOS PASOS:
- [ ] Deploy a Streamlit Cloud (24/7 online gratis)
- [ ] Agregar más empresas a la base de datos
- [ ] Integrar scraping de directorios públicos
- [ ] Sistema de deduplicación entre sesiones
- [ ] Dashboard de métricas de campaña

### 💡 NOTAS IMPORTANTES:
1. **Hunter.io NO provee teléfonos** — Solo emails y LinkedIn personal
2. **Créditos limitados** — 50 búsquedas/mes en plan gratuito
3. **Los leads excluidos se guardan** en leads_excluidos.json (persiste)
4. **El usuario quiere flujo simple** — Solo seleccionar país y buscar

### 🔄 CÓMO CONTINUAR:
1. Leer este archivo CONTEXTO.md
2. Ejecutar `streamlit run app.py`
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
