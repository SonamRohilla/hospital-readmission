-- =====================================================================
-- 03_risk_score.sql
-- A simple, explainable readmission risk score that care teams can
-- calculate at discharge - adapted from the LACE index
-- (van Walraven et al., 2010, CMAJ):
--
--   L  Length of stay          (0-7 points)
--   A  Acuity of admission     (3 points if emergency)
--   C  Comorbidity             (0-5 points; proxy = number of recorded diagnoses,
--                               because the Charlson index is not in this data)
--   E  Emergency visits        (0-4 points, prior year)
--
-- Validated against actual 30-day readmission. The Python model in
-- analysis/ is compared against this baseline.
-- =====================================================================

CREATE OR REPLACE TABLE risk_scores AS
WITH points AS (
    SELECT
        encounter_id,
        patient_nbr,
        readmitted_30d,
        CASE WHEN los_days < 1  THEN 0
             WHEN los_days = 1  THEN 1
             WHEN los_days = 2  THEN 2
             WHEN los_days = 3  THEN 3
             WHEN los_days <= 6 THEN 4
             WHEN los_days <= 13 THEN 5
             ELSE 7 END                                           AS l_points,
        CASE WHEN admission_type_group = 'Emergency / trauma'
               OR admission_source_group = 'Emergency room' THEN 3 ELSE 0 END AS a_points,
        CASE WHEN number_diagnoses <= 3 THEN 0
             WHEN number_diagnoses <= 5 THEN 1
             WHEN number_diagnoses <= 7 THEN 2
             WHEN number_diagnoses = 8  THEN 3
             ELSE 5 END                                           AS c_points,
        LEAST(prior_emergency, 4)                                 AS e_points
    FROM cohort
)
SELECT
    *,
    l_points + a_points + c_points + e_points                     AS lace_score,
    CASE WHEN l_points + a_points + c_points + e_points >= 10 THEN 'High (10+)'
         WHEN l_points + a_points + c_points + e_points >= 5  THEN 'Moderate (5-9)'
         ELSE 'Low (0-4)' END                                     AS risk_band
FROM points;

-- Validation: readmission rate per risk band
CREATE OR REPLACE TABLE risk_band_validation AS
SELECT
    risk_band,
    COUNT(*)                                            AS patients,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)  AS share_of_patients_pct,
    SUM(CAST(readmitted_30d AS INT))                    AS readmitted,
    ROUND(100.0 * AVG(CAST(readmitted_30d AS INT)), 2)  AS readmission_rate_pct
FROM risk_scores
GROUP BY risk_band
ORDER BY MIN(lace_score);
