# Scraper de Convocatorias Internacionales y Nacionales para Investigación

Este repositorio contiene un conjunto de scripts en Python que permiten
consultar convocatorias de financiación para investigación tanto en portales
internacionales como en ministerios colombianos. La interfaz se construye
con Tkinter, y ofrece dos modos de operación: Internacional y
Nacional. En el modo internacional se consulta la Comisión Europea,
Wellcome Trust, la Academia de Finlandia (AKA), ANR, IBRO e IDRC; en el modo
nacional se revisan varias páginas oficiales de ministerios colombianos. El
programa resume las descripciones de las convocatorias y clasifica cada
convocatoria de acuerdo con los Objetivos de Desarrollo Sostenible (ODS) a
partir de palabras clave
raw.githubusercontent.com
. Los resultados pueden
guardarse en ficheros CSV para consultarlos posteriormente sin volver a
scrapear las páginas web.

## Requisitos de instalación

Antes de ejecutar la aplicación es necesario instalar Python 3.8 o superior y
varias bibliotecas. Se recomienda crear un entorno virtual para aislar las
dependencias. Las bibliotecas que utiliza el proyecto incluyen:

- Tkinter – interfaz gráfica (incluida con Python).

- selenium – para automatizar el navegador en los portales que requieren
interacción dinámica; se configura un ChromeDriver en modo headless para
evitar ventanas de navegador
raw.githubusercontent.com
.

- requests y BeautifulSoup – empleados por los scrapers que usan
HTTP simple; se establece una cabecera de User‑Agent para reducir
bloqueos por parte de los servidores
raw.githubusercontent.com
.

- bs4 (BeautifulSoup4) – análisis de HTML.

Para instalar las dependencias básicas en un entorno virtual puede ejecutar
los siguientes comandos:

```bash
python3 -m venv venv
source venv/bin/activate
pip install selenium requests beautifulsoup4 
```
Nota sobre Selenium: el código utiliza un controlador de Google
Chrome en modo “headless”. Es necesario tener instalado Chrome
(o Chromium) y disponer de un ejecutable de chromedriver compatible en
el PATH del sistema. Consulte la [documentación de Selenium](https://selenium-python.readthedocs.io) para
instalar el controlador correspondiente.


