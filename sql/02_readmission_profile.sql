-- =====================================================================
-- 02_readmission_profile.sql
-- 30-day readmission rate overall and by patient / stay characteristics.
-- Output is one long table: dimension | category | patients | readmitted | rate
-- =====================================================================

CREATE OR REPLACE TABLE kpi_overall AS
SELECT
    COUNT(*)                                            AS patients,
    SUM(CAST(readmitted_30d AS INT))                    AS readmitted_30d,
    ROUND(100.0 * AVG(CAST(readmitted_30d AS INT)), 2)  AS readmission_rate_pct,
    ROUND(AVG(los_days), 2)                             AS avg_los_days,
    ROUND(100.0 * AVG(CAST(hba1c_tested AS INT)), 1)    AS hba1c_tested_pct
FROM cohort;

CREATE OR REPLACE TABLE readmission_profile AS
WITH long AS (
    SELECT 'Age group' AS dimension, age_band AS category, readmitted_30d FROM cohort
    UNION ALL SELECT 'Primary diagnosis', primary_diagnosis_group, readmitted_30d FROM cohort
    UNION ALL SELECT 'Admission source', admission_source_group, readmitted_30d FROM cohort
    UNION ALL SELECT 'Discharged to', discharge_group, readmitted_30d FROM cohort
    UNION ALL SELECT 'Inpatient stays in prior year',
                     CASE WHEN prior_inpatient = 0 THEN '0'
                          WHEN prior_inpatient = 1 THEN '1'
                          WHEN prior_inpatient = 2 THEN '2'
                          ELSE '3+' END, readmitted_30d FROM cohort
    UNION ALL SELECT 'Emergency visits in prior year',
                     CASE WHEN prior_emergency = 0 THEN '0'
                          WHEN prior_emergency = 1 THEN '1'
                          ELSE '2+' END, readmitted_30d FROM cohort
    UNION ALL SELECT 'Length of stay',
                     CASE WHEN los_days <= 2 THEN '1-2 days'
                          WHEN los_days <= 4 THEN '3-4 days'
                          WHEN los_days <= 7 THEN '5-7 days'
                          ELSE '8-14 days' END, readmitted_30d FROM cohort
    UNION ALL SELECT 'HbA1c test', CASE WHEN hba1c_tested THEN 'Tested' ELSE 'Not tested' END, readmitted_30d FROM cohort
)
SELECT
    dimension,
    category,
    COUNT(*)                                            AS patients,
    SUM(CAST(readmitted_30d AS INT))                    AS readmitted,
    ROUND(100.0 * AVG(CAST(readmitted_30d AS INT)), 2)  AS readmission_rate_pct
FROM long
GROUP BY dimension, category
HAVING COUNT(*) >= 100          -- hide tiny groups (unstable rates)
ORDER BY dimension, category;
