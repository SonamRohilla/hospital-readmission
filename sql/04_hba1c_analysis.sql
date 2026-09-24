-- =====================================================================
-- 04_hba1c_analysis.sql
-- Replicating the question from the original paper (Strack et al., 2014):
-- is measuring HbA1c during the stay associated with fewer readmissions?
--
-- This is OBSERVATIONAL data, not an experiment: patients who were tested
-- may differ from those who were not. The raw comparison below is therefore
-- adjusted for age, diagnosis, admission source, discharge and length of stay
-- in analysis/model_and_stats.py (logistic regression).
-- =====================================================================

CREATE OR REPLACE TABLE hba1c_groups AS
SELECT
    CASE
        WHEN NOT hba1c_tested                         THEN '1. Not tested'
        WHEN hba1c_result = 'Norm'                    THEN '2. Tested - normal'
        WHEN NOT medication_changed                   THEN '3. Tested - high, no medication change'
        ELSE                                               '4. Tested - high, medication changed'
    END                                               AS hba1c_group,
    primary_diagnosis_group,
    readmitted_30d
FROM cohort;

-- overall
CREATE OR REPLACE TABLE hba1c_summary AS
SELECT
    hba1c_group,
    COUNT(*)                                            AS patients,
    ROUND(100.0 * AVG(CAST(readmitted_30d AS INT)), 2)  AS readmission_rate_pct
FROM hba1c_groups
GROUP BY hba1c_group
ORDER BY hba1c_group;

-- by primary diagnosis (the paper found the effect depends on the diagnosis)
CREATE OR REPLACE TABLE hba1c_by_diagnosis AS
SELECT
    primary_diagnosis_group,
    ROUND(100.0 * AVG(CAST(readmitted_30d AS INT)) FILTER (WHERE hba1c_group = '1. Not tested'), 2) AS not_tested_pct,
    ROUND(100.0 * AVG(CAST(readmitted_30d AS INT)) FILTER (WHERE hba1c_group <> '1. Not tested'), 2) AS tested_pct,
    COUNT(*) FILTER (WHERE hba1c_group <> '1. Not tested')                                          AS tested_patients,
    COUNT(*)                                                                                        AS patients
FROM hba1c_groups
WHERE primary_diagnosis_group IN ('Diabetes', 'Circulatory', 'Respiratory', 'Digestive', 'Injury', 'Other')
GROUP BY primary_diagnosis_group
ORDER BY patients DESC;
