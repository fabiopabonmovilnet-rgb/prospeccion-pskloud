# 📧 PSKloud Prospector - Sistema de Prospección B2B

Sistema completo de prospección y automatización de correos en frío estilo **Apollo.io**, personalizado para el mercado de software en **Latinoamérica** (Costa Rica y El Salvador).

## 🚀 Características

### Componente 1: Motor de Búsqueda de Leads
- Filtros por País, Tipo de Target, Sector y Cargo
- Base de datos simulada con +30 empresas reales
- Exportación a CSV y Excel

### Componente 2: Configurador de Campañas
- Plantillas de correo con variables dinámicas (`{{nombre}}`, `{{empresa}}`, `{{pais}}`, `{{cargo}}`)
- Plantilla optimizada para PSKloud incluida por defecto
- Vista previa en tiempo real

### Componente 3: Motor de Envío Masivo
- Envío vía SMTP real o modo simulación
- Barra de progreso y logs en tiempo real
- Estadísticas de éxito/fallo

## 📦 Instalación

```bash
pip install streamlit pandas openpyxl
```

## ▶️ Ejecución

```bash
streamlit run app.py
```

## 🏗️ Arquitectura

```
prospeccion-pskloud/
├── app.py              # Aplicación principal Streamlit
├── requirements.txt    # Dependencias
├── README.md           # Documentación
└── .gitignore          # Archivos ignorados
```

## 🇨🇷🇸🇻 Mercado Objetivo

- **Costa Rica**: 16 contactos en 12 empresas
- **El Salvador**: 16 contactos en 12 empresas
- Sectores: Tecnología, Retail, Finanzas, Salud, Turismo, Manufactura, Logística, Agricultura, Construcción, Contadores

## ⚠️ Nota

En modo simulación, el sistema genera logs realistas sin enviar correos reales. Para envío real, configure credenciales SMTP válidas.
