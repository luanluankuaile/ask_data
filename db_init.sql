CREATE TABLE IF NOT EXISTS students
(
    id character varying COLLATE pg_catalog."default" NOT NULL,
    name text COLLATE pg_catalog."default" NOT NULL,
    is_active boolean NOT NULL,
    enroll_date date NOT NULL,
    graduate_date date,
    CONSTRAINT students_pkey PRIMARY KEY (id)
);

INSERT INTO students (id, name, is_active, enroll_date, graduate_date) VALUES
(10001, 'Tom', TRUE, '2020-09-01', '2024-09-21'),
(10002, 'Alice', TRUE, '2021-03-15', '2025-07-10'),
(10003, 'Bob', FALSE, '2019-08-20', '2023-06-30'),
(10004, 'Carol', TRUE, '2022-01-10', '2026-05-25'),
(10005, 'David', FALSE, '2018-09-01', '2022-09-01'),
(10006, 'Eve', TRUE, '2020-09-01', '2024-09-21'),
(10007, 'Frank', TRUE, '2021-09-01', '2025-09-21'),
(10008, 'Grace', FALSE, '2017-09-01', '2021-09-21'),
(10009, 'Heidi', TRUE, '2022-09-01', '2026-09-21'),
(10010, 'Ivan', FALSE, '2016-09-01', '2020-09-21');

CREATE TABLE weather (
    id SERIAL PRIMARY KEY,
    location VARCHAR(100) NOT NULL,
    date DATE NOT NULL,
    weather VARCHAR(50) NOT NULL
);

INSERT INTO weather (location, date, weather) VALUES
('Beijing', '2025-12-01', 'Sunny'),
('Shanghai', '2025-12-01', 'Cloudy'),
('Guangzhou', '2025-12-01', 'Rainy'),
('Beijing', '2025-12-02', 'Snowy'),
('Shanghai', '2025-12-02', 'Sunny'),
('Guangzhou', '2025-12-02', 'Cloudy'),
('Beijing', '2025-12-03', 'Cloudy'),
('Shanghai', '2025-12-03', 'Rainy'),
('Guangzhou', '2025-12-03', 'Sunny');



-- Schema metadata table for storing business meanings of tables and columns
-- This table helps LLM understand the business context when generating SQL

CREATE TABLE IF NOT EXISTS schema_metadata (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(255) NOT NULL,
    column_name VARCHAR(255),  -- NULL means this is a table-level description
    business_name VARCHAR(255) NOT NULL,
    business_description TEXT NOT NULL,
    data_type VARCHAR(100),
    is_primary_key BOOLEAN DEFAULT FALSE,
    is_foreign_key BOOLEAN DEFAULT FALSE,
    foreign_key_reference VARCHAR(255),  -- format: "table_name.column_name"
    sample_values TEXT,  -- JSON array of sample values
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(table_name, column_name)
);

-- Insert metadata for students table
INSERT INTO schema_metadata (table_name, column_name, business_name, business_description, data_type, is_primary_key, sample_values) 
VALUES 
    ('students', NULL, 'Students Table', 'Stores all student basic information and enrollment details', NULL, FALSE, NULL),
    ('students', 'id', 'Student ID', 'Unique identifier for each student, auto-generated primary key', 'INTEGER', TRUE, '["1", "2", "3"]'),
    ('students', 'name', 'Student Name', 'Full name of the student', 'TEXT/VARCHAR', FALSE, '["Alice Johnson", "Bob Smith", "Charlie Brown"]'),
    ('students', 'enroll_date', 'Enrollment Date', 'The date when student enrolled, used for statistics by enrollment year', 'DATE/INTEGER', FALSE, '["2020-09-01", "2021-09-01", "2022-09-01"]'),
    ('students', 'is_active', 'Active Status', 'Indicates whether the student is currently active or inactive', 'BOOLEAN', FALSE, '["true", "false"]'),
    ('students', 'graduate_date', 'Graduation Date', 'The date when student graduated or expected to graduate', 'DATE', FALSE, '["2024-06-15", "2025-06-15", "2026-06-15"]')
ON CONFLICT (table_name, column_name) DO UPDATE 
SET 
    business_name = EXCLUDED.business_name,
    business_description = EXCLUDED.business_description,
    data_type = EXCLUDED.data_type,
    is_primary_key = EXCLUDED.is_primary_key,
    sample_values = EXCLUDED.sample_values,
    updated_at = CURRENT_TIMESTAMP;

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_schema_metadata_table ON schema_metadata(table_name);

-- Insert metadata for weather table
INSERT INTO schema_metadata (
    table_name, column_name, business_name, business_description, data_type, is_primary_key, sample_values
) VALUES
('weather', NULL, 'Weather Records', 'Stores historical weather observation data for various cities and regions', NULL, FALSE, NULL),
('weather', 'id', 'Record ID', 'Primary key that uniquely identifies each weather record', 'SERIAL', TRUE, '1, 2, 3'),
('weather', 'location', 'Location', 'Name of the city or region where the weather is observed', 'VARCHAR(100)', FALSE, 'Beijing, Shanghai, Guangzhou'),
('weather', 'date', 'Date', 'Date of the weather observation', 'DATE', FALSE, '2025-12-01, 2025-12-02'),
('weather', 'weather', 'Weather', 'Description of the weather condition on the given date', 'VARCHAR(50)', FALSE, 'Sunny, Cloudy, Rainy, Snowy')
ON CONFLICT (table_name, column_name) DO UPDATE 
SET 
    business_name = EXCLUDED.business_name,
    business_description = EXCLUDED.business_description,
    data_type = EXCLUDED.data_type,
    is_primary_key = EXCLUDED.is_primary_key,
    sample_values = EXCLUDED.sample_values,
    updated_at = CURRENT_TIMESTAMP;
