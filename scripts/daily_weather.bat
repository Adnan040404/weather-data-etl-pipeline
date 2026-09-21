@echo off
REM Runs the pipeline once and appends the output to output\pipeline.log.
REM Point Windows Task Scheduler at this file to collect readings every day (or every few hours).
REM Edit the folder path on the next line to where you cloned the project.
cd /d C:\Work\weather-data-etl-pipeline
call .venv\Scripts\activate
python run_pipeline.py --source live >> output\pipeline.log 2>&1
