-- =====================================================================
-- 01_staging.sql
-- Clean encounters, join the three lookup tables, add readable groups,
-- then build the analysis cohort (one encounter per patient).
-- =====================================================================

CREATE OR REPLACE TABLE stg_encounters AS
SELECT
    CAST(e.encounter_id AS BIGINT)                                  AS encounter_id,
    CAST(e.patient_nbr  AS BIGINT)                                  AS patient_nbr,
    NULLIF(e.race, '?')                                             AS race,
    NULLIF(e.gender, 'Unknown/Invalid')                             AS gender,
    e.age                                                           AS age_band,          -- e.g. '[70-80)'
    CAST(REGEXP_EXTRACT(e.age, '\[(\d+)-', 1) AS INT) + 5           AS age_mid,           -- 75

    -- lookup joins -------------------------------------------------------
    CAST(e.admission_type_id AS INT)                                AS admission_type_id,
    t.description                                                   AS admission_type,
    CASE WHEN CAST(e.admission_type_id AS INT) IN (1, 7) THEN 'Emergency / trauma'
         WHEN CAST(e.admission_type_id AS INT) = 2       THEN 'Urgent'
         WHEN CAST(e.admission_type_id AS INT) = 3       THEN 'Elective'
         ELSE 'Unknown' END                                         AS admission_type_group,
    CAST(e.admission_source_id AS INT)                              AS admission_source_id,
    s.description                                                   AS admission_source,
    CASE WHEN CAST(e.admission_source_id AS INT) = 7                   THEN 'Emergency room'
         WHEN CAST(e.admission_source_id AS INT) IN (1, 2, 3)          THEN 'Referral'
         WHEN CAST(e.admission_source_id AS INT) IN (4, 5, 6, 10, 18, 22, 25, 26) THEN 'Transfer'
         ELSE 'Other / unknown' END                                 AS admission_source_group,
    CAST(e.discharge_disposition_id AS INT)                         AS discharge_disposition_id,
    d.description                                                   AS discharge_disposition,
    CASE WHEN CAST(e.discharge_disposition_id AS INT) = 1                  THEN 'Home'
         WHEN CAST(e.discharge_disposition_id AS INT) IN (6, 8)            THEN 'Home with health service'
         WHEN CAST(e.discharge_disposition_id AS INT) IN (3, 4, 5, 15, 22, 23, 24, 27, 28, 29, 30)
                                                                           THEN 'Care facility (SNF / rehab / other)'
         WHEN CAST(e.discharge_disposition_id AS INT) = 2                  THEN 'Other hospital'
         WHEN CAST(e.discharge_disposition_id AS INT) = 7                  THEN 'Left against medical advice'
         WHEN CAST(e.discharge_disposition_id AS INT) IN (11, 13, 14, 19, 20, 21) THEN 'Died / hospice'
         ELSE 'Other / unknown' END                                 AS discharge_group,

    -- stay ----------------------------------------------------------------
    CAST(e.time_in_hospital AS INT)                                 AS los_days,
    COALESCE(NULLIF(e.medical_specialty, '?'), 'Unknown')           AS medical_specialty,
    CAST(e.num_lab_procedures AS INT)                               AS num_lab_procedures,
    CAST(e.num_procedures AS INT)                                   AS num_procedures,
    CAST(e.num_medications AS INT)                                  AS num_medications,
    CAST(e.number_diagnoses AS INT)                                 AS number_diagnoses,

    -- utilisation in the year before this admission
    CAST(e.number_outpatient AS INT)                                AS prior_outpatient,
    CAST(e.number_emergency  AS INT)                                AS prior_emergency,
    CAST(e.number_inpatient  AS INT)                                AS prior_inpatient,

    -- primary diagnosis grouped by ICD-9 chapter (same grouping as Strack et al., 2014)
    e.diag_1,
    CASE
        WHEN e.diag_1 = '?'                                          THEN 'Missing'
        WHEN e.diag_1 LIKE 'V%' OR e.diag_1 LIKE 'E%'                THEN 'Other'
        WHEN e.diag_1 LIKE '250%'                                    THEN 'Diabetes'
        WHEN TRY_CAST(e.diag_1 AS DOUBLE) BETWEEN 390 AND 459
          OR TRY_CAST(e.diag_1 AS DOUBLE) BETWEEN 785 AND 785.99     THEN 'Circulatory'
        WHEN TRY_CAST(e.diag_1 AS DOUBLE) BETWEEN 460 AND 519
          OR TRY_CAST(e.diag_1 AS DOUBLE) BETWEEN 786 AND 786.99     THEN 'Respiratory'
        WHEN TRY_CAST(e.diag_1 AS DOUBLE) BETWEEN 520 AND 579
          OR TRY_CAST(e.diag_1 AS DOUBLE) BETWEEN 787 AND 787.99     THEN 'Digestive'
        WHEN TRY_CAST(e.diag_1 AS DOUBLE) BETWEEN 800 AND 999.99     THEN 'Injury'
        WHEN TRY_CAST(e.diag_1 AS DOUBLE) BETWEEN 710 AND 739.99     THEN 'Musculoskeletal'
        WHEN TRY_CAST(e.diag_1 AS DOUBLE) BETWEEN 580 AND 629.99
          OR TRY_CAST(e.diag_1 AS DOUBLE) BETWEEN 788 AND 788.99     THEN 'Genitourinary'
        WHEN TRY_CAST(e.diag_1 AS DOUBLE) BETWEEN 140 AND 239.99     THEN 'Neoplasms'
        ELSE 'Other'
    END                                                             AS primary_diagnosis_group,

    -- diabetes care -----------------------------------------------------
    e.A1Cresult                                                     AS hba1c_result,       -- None / Norm / >7 / >8
    e.A1Cresult <> 'None'                                           AS hba1c_tested,
    e.change = 'Ch'                                                 AS medication_changed,
    e.diabetesMed = 'Yes'                                           AS on_diabetes_medication,
    e.insulin                                                       AS insulin,            -- No / Steady / Up / Down

    -- outcome -------------------------------------------------------------
    e.readmitted                                                    AS readmitted_raw,     -- NO / >30 / <30
    e.readmitted = '<30'                                            AS readmitted_30d
FROM raw_encounters e
LEFT JOIN raw_admission_type        t ON CAST(e.admission_type_id AS INT)        = t.admission_type_id
LEFT JOIN raw_admission_source      s ON CAST(e.admission_source_id AS INT)      = s.admission_source_id
LEFT JOIN raw_discharge_disposition d ON CAST(e.discharge_disposition_id AS INT) = d.discharge_disposition_id;


-- ---------------------------------------------------------------------
-- Analysis cohort
--  * first encounter per patient (encounter_id increases over time)
--  * patients who died or went to hospice are excluded (cannot be readmitted)
--  * invalid gender excluded
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE cohort AS
WITH ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY patient_nbr ORDER BY encounter_id) AS encounter_seq
    FROM stg_encounters
)
SELECT * EXCLUDE (encounter_seq)
FROM ranked
WHERE encounter_seq = 1
  AND discharge_group <> 'Died / hospice'
  AND gender IS NOT NULL;


-- How many rows each step removes (shown in the README and dashboard)
CREATE OR REPLACE TABLE cohort_funnel AS
SELECT 1 AS step, 'All hospital encounters' AS description, COUNT(*) AS encounters FROM stg_encounters
UNION ALL
SELECT 2, 'First encounter per patient', COUNT(DISTINCT patient_nbr) FROM stg_encounters
UNION ALL
SELECT 3, 'Excluding died / hospice and invalid gender', COUNT(*) FROM cohort
ORDER BY step;
