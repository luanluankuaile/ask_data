-- Class table: stores class information
CREATE TABLE IF NOT EXISTS class (
    id SERIAL PRIMARY KEY,
    class_name VARCHAR(100) NOT NULL UNIQUE,
    grade INTEGER NOT NULL,
    homeroom_teacher_id INTEGER,
    is_active BOOLEAN DEFAULT TRUE
);

INSERT INTO class (class_name, grade, homeroom_teacher_id, is_active) VALUES
('Grade1-ClassA', 1, 1, TRUE),
('Grade1-ClassB', 1, 4, TRUE),
('Grade2-ClassA', 2, 2, TRUE),
('Grade2-ClassB', 2, 5, TRUE),
('Grade3-ClassA', 3, 3, TRUE),
('Grade3-ClassB', 3, 9, TRUE),
('Grade4-ClassA', 4, 13, TRUE);

-- Student table with class_id
CREATE TABLE IF NOT EXISTS student
(
    id character varying COLLATE pg_catalog."default" NOT NULL,
    name text COLLATE pg_catalog."default" NOT NULL,
    class_id INTEGER,
    is_active boolean NOT NULL,
    enroll_date date NOT NULL,
    graduate_date date,
    CONSTRAINT students_pkey PRIMARY KEY (id),
    CONSTRAINT fk_student_class FOREIGN KEY (class_id) REFERENCES class(id)
);

INSERT INTO student (id, name, class_id, is_active, enroll_date, graduate_date) VALUES
(10001, 'Tom', 1, TRUE, '2020-09-01', '2024-09-21'),
(10002, 'Alice', 1, TRUE, '2021-03-15', '2025-07-10'),
(10003, 'Bob', 5, FALSE, '2019-08-20', '2023-06-30'),
(10004, 'Carol', 3, TRUE, '2022-01-10', '2026-05-25'),
(10005, 'David', 3, FALSE, '2018-09-01', '2022-09-01'),
(10006, 'Eve', 2, TRUE, '2020-09-01', '2024-09-21'),
(10007, 'Frank', 2, TRUE, '2021-09-01', '2025-09-21'),
(10008, 'Grace', 6, FALSE, '2017-09-01', '2021-09-21'),
(10009, 'Heidi', 3, TRUE, '2022-09-01', '2026-09-21'),
(10010, 'Ivan', 7, FALSE, '2016-09-01', '2020-09-21'),
(10011, 'Jack', 4, TRUE, '2022-09-01', '2026-09-21'),
(10012, 'Kelly', 4, TRUE, '2022-09-01', '2026-09-21'),
(10013, 'Linda', 5, TRUE, '2023-09-01', '2027-09-21'),
(10014, 'Mike', 5, TRUE, '2023-09-01', '2027-09-21'),
(10015, 'Nancy', 6, TRUE, '2023-09-01', '2027-09-21'),
(10016, 'Oscar', 6, TRUE, '2023-09-01', '2027-09-21'),
(10017, 'Paul', 7, TRUE, '2024-09-01', '2028-09-21'),
(10018, 'Queen', 7, TRUE, '2024-09-01', '2028-09-21'),
(10019, 'Rose', 7, TRUE, '2024-09-01', '2028-09-21'),
(10020, 'Steve', 7, TRUE, '2024-09-01', '2028-09-21');

CREATE TABLE IF NOT EXISTS teacher (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    teach_course VARCHAR(100) NOT NULL,
    title VARCHAR(50) NOT NULL,
    teach_years INTEGER NOT NULL
);
INSERT INTO teacher (name, teach_course, title, teach_years) VALUES
('Dr. Alice Johnson', 'Computer Science', 'Professor', 15),
('Prof. Bob Smith', 'Mathematics', 'Associate Professor', 12),
('Dr. Carol White', 'Physics', 'Professor', 20),
('Mr. David Brown', 'English Literature', 'Lecturer', 5),
('Dr. Emma Davis', 'Chemistry', 'Assistant Professor', 8),
('Prof. Frank Wilson', 'History', 'Professor', 18),
('Dr. Grace Lee', 'Biology', 'Associate Professor', 10),
('Ms. Helen Chen', 'Art', 'Lecturer', 6),
('Dr. Isaac Martinez', 'Economics', 'Professor', 22),
('Prof. Julia Garcia', 'Psychology', 'Associate Professor', 14),
('Dr. Kevin Taylor', 'Computer Science', 'Assistant Professor', 7),
('Mr. Laura Anderson', 'Music', 'Lecturer', 4),
('Dr. Michael Thomas', 'Engineering', 'Professor', 25),
('Prof. Nancy Jackson', 'Philosophy', 'Associate Professor', 11),
('Dr. Oliver Harris', 'Statistics', 'Assistant Professor', 9),
('Ms. Patricia Martin', 'Geography', 'Lecturer', 3),
('Dr. Quinn Robinson', 'Political Science', 'Professor', 16),
('Prof. Rachel Clark', 'Sociology', 'Associate Professor', 13),
('Dr. Samuel Lewis', 'Mathematics', 'Professor', 19),
('Ms. Teresa Walker', 'Physical Education', 'Lecturer', 8);

-- Course table: stores course information 
CREATE TABLE IF NOT EXISTS course (
    id SERIAL PRIMARY KEY,
    course_code VARCHAR(50) NOT NULL UNIQUE,
    course_name VARCHAR(100) NOT NULL,
    credits INTEGER DEFAULT 3,
    department VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE
);

INSERT INTO course (course_code, course_name, credits, department, is_active) VALUES
('CS101', 'Introduction to Computer Science', 4, 'Computer Science', TRUE),
('CS201', 'Data Structures', 4, 'Computer Science', TRUE),
('MATH101', 'Calculus I', 4, 'Mathematics', TRUE),
('MATH201', 'Linear Algebra', 3, 'Mathematics', TRUE),
('PHY101', 'Physics I', 4, 'Physics', TRUE),
('PHY201', 'Physics II', 4, 'Physics', TRUE),
('ENG101', 'English Literature', 3, 'English', TRUE),
('ENG201', 'Creative Writing', 3, 'English', TRUE),
('CHEM101', 'General Chemistry', 4, 'Chemistry', TRUE),
('HIST101', 'World History', 3, 'History', TRUE),
('BIO101', 'Biology Fundamentals', 4, 'Biology', TRUE),
('ART101', 'Introduction to Art', 2, 'Art', TRUE),
('ECON101', 'Microeconomics', 3, 'Economics', TRUE),
('PSY101', 'Introduction to Psychology', 3, 'Psychology', TRUE),
('PE101', 'Physical Education', 1, 'Physical Education', TRUE);

-- Course enrollment table: student select courses
CREATE TABLE IF NOT EXISTS course_enrollment (
    id SERIAL PRIMARY KEY,
    student_id VARCHAR NOT NULL,
    course_id INTEGER NOT NULL,
    teacher_id INTEGER,
    grade INTEGER NOT NULL,
    semester VARCHAR(20),
    enrollment_date DATE DEFAULT CURRENT_DATE,
    score VARCHAR(5),
    is_active BOOLEAN DEFAULT TRUE,
    CONSTRAINT fk_course_enrollment_student FOREIGN KEY (student_id) REFERENCES student(id),
    CONSTRAINT fk_course_enrollment_course FOREIGN KEY (course_id) REFERENCES course(id),
    CONSTRAINT fk_course_enrollment_teacher FOREIGN KEY (teacher_id) REFERENCES teacher(id),
    CONSTRAINT unique_student_course_semester UNIQUE(student_id, course_id, semester)
);

INSERT INTO course_enrollment (student_id, course_id, teacher_id, grade, semester, score, is_active) VALUES
('10001', 1, 1, 1, '2020-Fall', 'A', TRUE),
('10001', 3, 2, 1, '2020-Fall', 'B+', TRUE),
('10001', 7, 4, 1, '2020-Fall', 'A-', TRUE),
('10002', 1, 1, 1, '2021-Spring', 'A-', TRUE),
('10002', 9, 5, 1, '2021-Spring', 'B', TRUE),
('10002', 12, 8, 1, '2021-Spring', 'A', TRUE),
('10004', 2, 11, 2, '2022-Fall', 'A', TRUE),
('10004', 4, 2, 2, '2022-Fall', 'B+', TRUE),
('10004', 10, 6, 2, '2022-Fall', 'A-', TRUE),
('10006', 1, 1, 1, '2020-Fall', 'B', TRUE),
('10006', 11, 7, 1, '2020-Fall', 'A', TRUE),
('10007', 3, 2, 1, '2021-Fall', 'A', TRUE),
('10007', 12, 8, 1, '2021-Fall', 'A+', TRUE),
('10009', 4, 19, 2, '2022-Fall', 'A-', TRUE),
('10009', 14, 10, 2, '2022-Fall', 'B+', TRUE),
('10011', 2, 11, 2, '2022-Fall', 'B', TRUE),
('10011', 13, 9, 2, '2022-Fall', 'A', TRUE),
('10012', 4, 2, 2, '2022-Fall', 'A', TRUE),
('10012', 5, 3, 2, '2022-Fall', 'B+', TRUE),
('10013', 6, 3, 3, '2023-Fall', 'A', TRUE),
('10013', 8, 4, 3, '2023-Fall', 'A-', TRUE),
('10014', 1, 1, 3, '2023-Fall', 'B+', TRUE),
('10014', 3, 19, 3, '2023-Fall', 'A', TRUE),
('10015', 14, 10, 3, '2023-Fall', 'A', TRUE),
('10015', 15, 20, 3, '2023-Fall', 'A+', TRUE),
('10016', 13, 9, 3, '2023-Fall', 'B', TRUE),
('10016', 5, 3, 3, '2023-Fall', 'A-', TRUE),
('10017', 2, 11, 4, '2024-Fall', NULL, TRUE),
('10017', 4, 2, 4, '2024-Fall', NULL, TRUE),
('10018', 6, 3, 4, '2024-Fall', NULL, TRUE),
('10018', 8, 4, 4, '2024-Fall', NULL, TRUE),
('10019', 1, 1, 4, '2024-Fall', NULL, TRUE),
('10019', 7, 4, 4, '2024-Fall', NULL, TRUE),
('10020', 3, 19, 4, '2024-Fall', NULL, TRUE),
('10020', 11, 7, 4, '2024-Fall', NULL, TRUE);


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
INSERT INTO schema_metadata (table_name, column_name, business_name, business_description, data_type, is_primary_key, is_foreign_key, foreign_key_reference, sample_values) 
VALUES 
    ('student', NULL, 'Students Table', 'Stores all student basic information and class assignment', NULL, FALSE, FALSE, NULL, NULL),
    ('student', 'id', 'Student ID', 'Unique identifier for each student, primary key', 'VARCHAR', TRUE, FALSE, NULL, '["10001", "10002", "10003"]'),
    ('student', 'name', 'Student Name', 'Full name of the student', 'TEXT', FALSE, FALSE, NULL, '["Tom", "Alice", "Bob"]'),
    ('student', 'class_id', 'Class ID', 'Foreign key reference to the class the student belongs to', 'INTEGER', FALSE, TRUE, 'class.id', '["1", "2", "3"]'),
    ('student', 'enroll_date', 'Enrollment Date', 'The date when student enrolled, used for statistics by enrollment year', 'DATE', FALSE, FALSE, NULL, '["2020-09-01", "2021-09-01", "2022-09-01"]'),
    ('student', 'is_active', 'Active Status', 'Indicates whether the student is currently active or graduated', 'BOOLEAN', FALSE, FALSE, NULL, '["true", "false"]'),
    ('student', 'graduate_date', 'Graduation Date', 'The date when student graduated or expected to graduate', 'DATE', FALSE, FALSE, NULL, '["2024-06-15", "2025-06-15", "2026-06-15"]')
ON CONFLICT (table_name, column_name) DO UPDATE 
SET 
    business_name = EXCLUDED.business_name,
    business_description = EXCLUDED.business_description,
    data_type = EXCLUDED.data_type,
    is_primary_key = EXCLUDED.is_primary_key,
    is_foreign_key = EXCLUDED.is_foreign_key,
    foreign_key_reference = EXCLUDED.foreign_key_reference,
    sample_values = EXCLUDED.sample_values,
    updated_at = CURRENT_TIMESTAMP;

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_schema_metadata_table ON schema_metadata(table_name);

-- Insert metadata for teacher table
INSERT INTO schema_metadata (
    table_name, column_name, business_name, business_description, data_type, is_primary_key, sample_values
) VALUES
('teacher', NULL, 'Teachers Table', 'Stores faculty information including teaching experience, courses, and academic titles', NULL, FALSE, NULL),
('teacher', 'id', 'Teacher ID', 'Primary key that uniquely identifies each teacher', 'SERIAL', TRUE, '1, 2, 3'),
('teacher', 'name', 'Teacher Name', 'Full name of the teacher including academic title prefix', 'VARCHAR(100)', FALSE, 'Dr. Alice Johnson, Prof. Bob Smith, Mr. David Brown'),
('teacher', 'teach_course', 'Teaching Course', 'Primary course or subject area that the teacher specializes in', 'VARCHAR(100)', FALSE, 'Computer Science, Mathematics, Physics, English Literature'),
('teacher', 'title', 'Academic Title', 'Academic rank or position of the teacher', 'VARCHAR(50)', FALSE, 'Professor, Associate Professor, Assistant Professor, Lecturer'),
('teacher', 'teach_years', 'Teaching Years', 'Number of years of teaching experience', 'INTEGER', FALSE, '5, 10, 15, 20')
ON CONFLICT (table_name, column_name) DO UPDATE 
SET 
    business_name = EXCLUDED.business_name,
    business_description = EXCLUDED.business_description,
    data_type = EXCLUDED.data_type,
    is_primary_key = EXCLUDED.is_primary_key,
    sample_values = EXCLUDED.sample_values,
    updated_at = CURRENT_TIMESTAMP;

-- Insert metadata for class table
INSERT INTO schema_metadata (
    table_name, column_name, business_name, business_description, data_type, is_primary_key, is_foreign_key, foreign_key_reference, sample_values
) VALUES
('class', NULL, 'Class Table', 'Stores class information organized by grade level with assigned homeroom teachers', NULL, FALSE, FALSE, NULL, NULL),
('class', 'id', 'Class ID', 'Primary key that uniquely identifies each class', 'SERIAL', TRUE, FALSE, NULL, '1, 2, 3'),
('class', 'class_name', 'Class Name', 'Name of the class (e.g., Grade1-ClassA)', 'VARCHAR(100)', FALSE, FALSE, NULL, 'Grade1-ClassA, Grade2-ClassB, Grade3-ClassA'),
('class', 'grade', 'Grade Level', 'Grade level of the class (1=Freshman, 2=Sophomore, 3=Junior, 4=Senior)', 'INTEGER', FALSE, FALSE, NULL, '1, 2, 3, 4'),
('class', 'homeroom_teacher_id', 'Homeroom Teacher ID', 'Foreign key reference to the homeroom teacher for this class', 'INTEGER', FALSE, TRUE, 'teacher.id', '1, 2, 3'),
('class', 'is_active', 'Active Status', 'Indicates whether the class is currently active', 'BOOLEAN', FALSE, FALSE, NULL, 'true, false')
ON CONFLICT (table_name, column_name) DO UPDATE 
SET 
    business_name = EXCLUDED.business_name,
    business_description = EXCLUDED.business_description,
    data_type = EXCLUDED.data_type,
    is_primary_key = EXCLUDED.is_primary_key,
    is_foreign_key = EXCLUDED.is_foreign_key,
    foreign_key_reference = EXCLUDED.foreign_key_reference,
    sample_values = EXCLUDED.sample_values,
    updated_at = CURRENT_TIMESTAMP;

-- Insert metadata for course table
INSERT INTO schema_metadata (
    table_name, column_name, business_name, business_description, data_type, is_primary_key, sample_values
) VALUES
('course', NULL, 'Course Table', 'Stores all available courses with department and credit information', NULL, FALSE, NULL),
('course', 'id', 'Course ID', 'Primary key that uniquely identifies each course', 'SERIAL', TRUE, '1, 2, 3'),
('course', 'course_code', 'Course Code', 'Unique code identifier for the course (e.g., CS101, MATH201)', 'VARCHAR(50)', FALSE, 'CS101, MATH101, PHY101'),
('course', 'course_name', 'Course Name', 'Full name of the course', 'VARCHAR(100)', FALSE, 'Introduction to Computer Science, Calculus I, Physics I'),
('course', 'credits', 'Credits', 'Number of credits for completing this course', 'INTEGER', FALSE, '3, 4'),
('course', 'department', 'Department', 'Academic department that offers this course', 'VARCHAR(100)', FALSE, 'Computer Science, Mathematics, Physics'),
('course', 'is_active', 'Active Status', 'Indicates whether the course is currently being offered', 'BOOLEAN', FALSE, 'true, false')
ON CONFLICT (table_name, column_name) DO UPDATE 
SET 
    business_name = EXCLUDED.business_name,
    business_description = EXCLUDED.business_description,
    data_type = EXCLUDED.data_type,
    is_primary_key = EXCLUDED.is_primary_key,
    sample_values = EXCLUDED.sample_values,
    updated_at = CURRENT_TIMESTAMP;

-- Insert metadata for course_enrollment table
INSERT INTO schema_metadata (
    table_name, column_name, business_name, business_description, data_type, is_primary_key, is_foreign_key, foreign_key_reference, sample_values
) VALUES
('course_enrollment', NULL, 'Course Enrollment Table', 'Stores student course selections with teacher assignments, grades and scores', NULL, FALSE, FALSE, NULL, NULL),
('course_enrollment', 'id', 'Enrollment ID', 'Primary key that uniquely identifies each course enrollment record', 'SERIAL', TRUE, FALSE, NULL, '1, 2, 3'),
('course_enrollment', 'student_id', 'Student ID', 'Foreign key reference to the student taking the course', 'VARCHAR', FALSE, TRUE, 'students.id', '10001, 10002, 10003'),
('course_enrollment', 'course_id', 'Course ID', 'Foreign key reference to the course being taken', 'INTEGER', FALSE, TRUE, 'course.id', '1, 2, 3'),
('course_enrollment', 'teacher_id', 'Teacher ID', 'Foreign key reference to the teacher teaching this course section', 'INTEGER', FALSE, TRUE, 'teacher.id', '1, 2, 3'),
('course_enrollment', 'grade', 'Grade Level', 'Grade level when taking this course (1=Freshman, 2=Sophomore, 3=Junior, 4=Senior), should match class.grade', 'INTEGER', FALSE, FALSE, NULL, '1, 2, 3, 4'),
('course_enrollment', 'semester', 'Semester', 'Semester when the course is taken (e.g., 2020-Fall, 2021-Spring)', 'VARCHAR(20)', FALSE, FALSE, NULL, '2020-Fall, 2021-Spring, 2022-Fall'),
('course_enrollment', 'enrollment_date', 'Enrollment Date', 'Date when the student enrolled in this course', 'DATE', FALSE, FALSE, NULL, '2020-09-01, 2021-09-01'),
('course_enrollment', 'score', 'Course Score', 'Final score/grade received for the course (A, A-, B+, B, etc.)', 'VARCHAR(5)', FALSE, FALSE, NULL, 'A, A-, B+, B'),
('course_enrollment', 'is_active', 'Active Status', 'Indicates whether the enrollment is currently active', 'BOOLEAN', FALSE, FALSE, NULL, 'true, false')
ON CONFLICT (table_name, column_name) DO UPDATE 
SET 
    business_name = EXCLUDED.business_name,
    business_description = EXCLUDED.business_description,
    data_type = EXCLUDED.data_type,
    is_primary_key = EXCLUDED.is_primary_key,
    is_foreign_key = EXCLUDED.is_foreign_key,
    foreign_key_reference = EXCLUDED.foreign_key_reference,
    sample_values = EXCLUDED.sample_values,
    updated_at = CURRENT_TIMESTAMP;
