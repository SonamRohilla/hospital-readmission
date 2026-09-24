-- =====================================================================
-- 00_data_quality_checks.sql
-- Profile the raw hospital data before any analysis.
-- Each check counts affected rows and records how it is handled in 01_staging.sql.
-- raw tables: raw_encounters (all columns loaded as text), raw_admission_type,
--             raw_admission_source, raw_discharge_disposition
-- =====================================================================

CREATE OR REPLACE TABLE dq_results AS

SELECT 1 AS check_id, 'Duplicate encounter_id' AS check_name,
       COUNT(*) - COUNT(DISTINCT encounter_id) AS affected_rows,
       'None found - encounter_id is a valid primary key' AS handling
FROM raw_encounters

UNION ALL
SELECT 2, 'Race recorded as ''?''', COUNT(*) FILTER (WHERE race = '?'),
       'Set to NULL, reported as Unknown'
FROM raw_encounters

UNION ALL
SELECT 3, 'Weight recorded as ''?''', COUNT(*) FILTER (WHERE weight = '?'),
       'Column dropped - 97% missing, not usable'
FROM raw_encounters

UNION ALL
SELECT 4, 'Payer code recorded as ''?''', COUNT(*) FILTER (WHERE payer_code = '?'),
       'Column dropped - 40% missing and not needed for the question'
FROM raw_encounters

UNION ALL
SELECT 5, 'Medical specialty recorded as ''?''', COUNT(*) FILTER (WHERE medical_specialty = '?'),
       'Kept as ''Unknown'' category (49% missing)'
FROM raw_encounters

UNION ALL
SELECT 6, 'Primary diagnosis (diag_1) recorded as ''?''', COUNT(*) FILTER (WHERE diag_1 = '?'),
       'Grouped as ''Missing'''
FROM raw_encounters

UNION ALL
SELECT 7, 'Gender ''Unknown/Invalid''', COUNT(*) FILTER (WHERE gender = 'Unknown/Invalid'),
       'Excluded from the analysis cohort'
FROM raw_encounters

UNION ALL
SELECT 8, 'Repeat encounters of the same patient',
       COUNT(*) - COUNT(DISTINCT patient_nbr),
       'Keep first encounter per patient so observations are independent'
FROM raw_encounters

UNION ALL
SELECT 9, 'Discharged as died or to hospice (cannot be readmitted)',
       COUNT(*) FILTER (WHERE CAST(discharge_disposition_id AS INT) IN (11, 13, 14, 19, 20, 21)),
       'Excluded from the analysis cohort'
FROM raw_encounters

UNION ALL
SELECT 10, 'Admission type unknown (NULL / Not Available / Not Mapped)',
       COUNT(*) FILTER (WHERE CAST(admission_type_id AS INT) IN (5, 6, 8)),
       'Grouped as ''Unknown'''
FROM raw_encounters

UNION ALL
SELECT 11, 'Admission source unknown (NULL / Not Available / Not Mapped / Invalid)',
       COUNT(*) FILTER (WHERE CAST(admission_source_id AS INT) IN (9, 15, 17, 20, 21)),
       'Grouped as ''Unknown'''
FROM raw_encounters

UNION ALL
SELECT 12, 'Discharge disposition unknown (NULL / Not Mapped / Invalid)',
       COUNT(*) FILTER (WHERE CAST(discharge_disposition_id AS INT) IN (18, 25, 26)),
       'Grouped as ''Unknown'''
FROM raw_encounters

UNION ALL
SELECT 13, 'Codes with no match in lookup tables (orphan keys)',
       COUNT(*) FILTER (WHERE t.admission_type_id IS NULL OR s.admission_source_id IS NULL
                           OR d.discharge_disposition_id IS NULL),
       'Checked with LEFT JOINs'
FROM raw_encounters e
LEFT JOIN raw_admission_type          t ON CAST(e.admission_type_id AS INT)        = t.admission_type_id
LEFT JOIN raw_admission_source        s ON CAST(e.admission_source_id AS INT)      = s.admission_source_id
LEFT JOIN raw_discharge_disposition   d ON CAST(e.discharge_disposition_id AS INT) = d.discharge_disposition_id

UNION ALL
SELECT 14, 'Lookup: same description used for two admission_source codes',
       (SELECT COUNT(*) FROM (SELECT description FROM raw_admission_source
                              GROUP BY description HAVING COUNT(*) > 1)),
       'Harmless (both mean Not Available) - mapped to the same group'

UNION ALL
SELECT 15, 'HbA1c test not performed (not an error - a care-quality signal)',
       COUNT(*) FILTER (WHERE A1Cresult = 'None'),
       'Kept - analysed in 04_hba1c_analysis.sql'
FROM raw_encounters;
