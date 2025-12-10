# Text to SQL - Student Management Query System

This repository provides a Streamlit application that translates natural-language queries into safe, read-only SQL statements. It uses LLM (Azure OpenAI or Deepseek) with Function Calling for intelligent SQL generation based on business-meaningful schema metadata, with automatic table identification to optimize token usage.

## Features

- 🤖 **LLM-Powered**: Supports Azure OpenAI GPT-4o and Deepseek with Function Calling
- 🔄 **Dual Provider**: Switch between Azure OpenAI and Deepseek via environment variable
- 📊 **Metadata-Driven**: Maintains schema_metadata table with business descriptions
- 🎯 **Smart Table Matching**: Automatically identifies relevant tables based on user prompt
- 🔒 **Safe Queries**: Only allows SELECT operations with security validation
- 🚀 **Token Optimized**: Loads only relevant table schemas to reduce token consumption
- 🌐 **Multi-Table Support**: Handles complex queries across students, classes, teachers, courses, and enrollments
- 📈 **Dynamic SQL Generation**: LLM generates SQL queries based on schema metadata instead of fixed function tools
- 🔗 **Relational Queries**: Supports JOIN operations between related tables
- 🛡️ **Robust Error Handling**: Network error detection and graceful fallback

## Configuration

Create a `.env` file in the project root with the following variables:

### Azure OpenAI (Default)

```bash
# Database connection (PostgreSQL recommended)
DATABASE_URI="postgresql://<user>:<pass>@<host>:<port>/<db>"

# LLM Provider: azure (default) or deepseek
LLM_PROVIDER=azure

# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY="your-api-key"
AZURE_OPENAI_ENDPOINT="your-azure-endpoint"
OPENAI_API_VERSION="2025-04-01-preview"
MODEL="gpt-4o"
```

### Deepseek Alternative

```bash
# Database connection
DATABASE_URI="postgresql://<user>:<pass>@<host>:<port>/<db>"

# LLM Provider
LLM_PROVIDER=deepseek

# Deepseek Configuration
DEEPSEEK_ENDPOINT="https://api.deepseek.com"
DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxx"
DEEPSEEK_MODEL="deepseek-chat"
```

### Switching Providers

Simply change `LLM_PROVIDER` in `.env` and restart the application:
- `LLM_PROVIDER=azure` - Use Azure OpenAI
- `LLM_PROVIDER=deepseek` - Use Deepseek

No code changes required!

## Setup

### 1. Install Dependencies

```bash
conda activate myenv
pip install -r requirements.txt
```

### 2. Initialize Database Schema

Run the database initialization script to create tables and metadata:

### DB init after install postgre
```bash
conda activate myenv
sudo -i -u postgres
psql -U postgres -d mydb
CREATE DATABASE mydb;
run sql in db_init.sql
```

```bash
# Connect to your PostgreSQL database and run:
psql -U <username> -d <database> -f db_init.sql
```

This creates:
- `class` table - Class information organized by grade
- `students` table - 20 students assigned to different classes
- `teacher` table - 20 teachers with various specializations
- `course` table - 15 courses across different departments
- `course_enrollment` table - Student course selections with grades and scores
- `schema_metadata` table - Business descriptions for all tables and columns

## Run Application

Start the Streamlit app:

```bash
# Standard mode
streamlit run app.py

# Headless mode (for servers)
python -m streamlit run app.py --server.port 8501 --server.headless true
```

## How It Works

### Architecture Overview

The system uses a **three-phase workflow** for token optimization:

```
User Question: "How many students in Grade 1 enrolled in Computer Science courses?"
  ↓
Phase 1: Get all table names
  → Returns: ['students', 'class', 'teacher', 'course', 'course_enrollment']
  ↓
Phase 2: LLM identifies relevant tables (Fuzzy Matching)
  → Prompt: "Available tables: students, class, course, course_enrollment..."
  → User question: mentions students, grade, courses
  → LLM identifies: students, course, course_enrollment
  ↓
Phase 3: Load detailed schema only for identified tables
  → Loads: 3 table schemas with metadata
  → Skips: class, teacher tables (saves ~40% tokens)
  ↓
Phase 4: Generate SQL with identified schema
  → SQL: SELECT COUNT(DISTINCT ce.student_id) FROM course_enrollment ce 
          JOIN course c ON ce.course_id = c.id 
          WHERE ce.grade = 1 AND c.department = 'Computer Science'
  ↓
Phase 5: Execute and return results
```

### Fuzzy Table Matching

The system performs **semantic matching** based on business descriptions:

| User Question | Table Identified | Reason |
|---------------|------------------|---------||
| "How many students in Grade 1?" | `students`, `class` | Direct mention + grade reference |
| "Which courses did Tom take?" | `students`, `course`, `course_enrollment` | Student name + course concept |
| "Teachers teaching Math" | `teacher`, `course` | Subject reference |
| "Average score in Computer Science" | `course`, `course_enrollment` | Course name + grade concept |

## Schema Metadata

The `schema_metadata` table stores business-meaningful descriptions:

| Field | Description | Example |
|-------|-------------|---------|
| table_name | Table name | `students` |
| column_name | Column name (NULL for table-level) | `enroll_date` |
| business_name | Business name | `Enrollment Date` |
| business_description | Business description | `The date when student enrolled` |
| data_type | Data type | `DATE` |
| is_primary_key | Primary key flag | `false` |
| sample_values | Example values | `"2020-09-01, 2021-09-01"` |

### Add New Tables

To add a new table with metadata:

```sql
-- 1. Create the table
CREATE TABLE courses (
    id SERIAL PRIMARY KEY,
    course_name VARCHAR(100) NOT NULL,
    credits INTEGER
);

-- 2. Add table-level metadata (required for table identification)
INSERT INTO schema_metadata (table_name, column_name, business_name, business_description)
VALUES ('courses', NULL, 'Course Information', 'Stores all course catalog data');

-- 3. Add column-level metadata
INSERT INTO schema_metadata 
(table_name, column_name, business_name, business_description, data_type, sample_values)
VALUES 
('courses', 'id', 'Course ID', 'Unique identifier for each course', 'SERIAL', '1, 2, 3'),
('courses', 'course_name', 'Course Name', 'Full name of the course', 'VARCHAR(100)', 'Mathematics, Physics, Chemistry'),
('courses', 'credits', 'Credits', 'Number of credits for the course', 'INTEGER', '3, 4, 5');
```

**Important**: Always include a table-level row (column_name = NULL) for the table to be discoverable by fuzzy matching.

## Example Queries

### Student Queries
- "How many students are in Grade1-ClassA?"
- "List all active students enrolled after 2020"
- "Show students who will graduate in 2024"
- "Which class does Tom belong to?"

### Course Queries
- "How many students enrolled in Computer Science courses?"
- "What courses are offered by the Mathematics department?"
- "Show all courses with 4 credits"

### Teacher Queries
- "Which teachers are Professors?"
- "Who is the homeroom teacher of Grade2-ClassA?"
- "List all teachers teaching Computer Science"

### Complex Multi-Table Queries
- "Which students in Grade 1 took courses taught by Dr. Alice Johnson?"
- "Show the average number of courses per student by grade"
- "List all courses taken by students in Grade1-ClassA"
- "How many students did each teacher teach in 2023-Fall semester?"

## Architecture

The system uses a **metadata-driven architecture** with dynamic SQL generation:

1. **Table Identification Phase**: LLM analyzes user prompt and identifies relevant tables based on business descriptions
   - Uses semantic matching: "enrollment" → students table
   - Reduces token usage by 70-90% for large schemas

2. **SQL Generation Phase**: LLM generates appropriate SQL query using schema metadata
   - Single `execute_query()` function tool replaces fixed function tools
   - LLM has full flexibility to generate any SELECT query

3. **Execution Phase**: Execute SQL with security validation and return results

4. **Response Phase**: LLM generates natural language response based on query results

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture documentation.

## Token Optimization

For databases with many tables, the system optimizes token usage:

| Scenario | Tables in DB | Tables Loaded | Token Savings |
|----------|--------------|---------------|---------------|
| Simple query ("How many students?") | 5 | 1 (students) | ~80% |
| Medium query ("Students in CS courses") | 5 | 3 (students, course, course_enrollment) | ~40% |
| Complex query ("All data") | 5 | 5 (all tables) | 0% |
| Enterprise (50+ tables) | 50 | 2-3 (relevant) | ~90-95% |

**Benefits:**
- Prevents token overflow for large schemas
- Faster response times (less data to process)
- Lower API costs
- Maintains query accuracy with fuzzy matching

## Safety Features

- ✅ Only SELECT queries allowed (INSERT/UPDATE/DELETE blocked)
- ✅ Forbidden keyword detection (DROP, ALTER, TRUNCATE, etc.)
- ✅ Single statement enforcement (prevents SQL injection)
- ✅ Parameterized queries via SQLAlchemy
- ✅ Read-only database operations
- ✅ LLM-generated SQL with validation

## Testing

Test the system with various queries:

```bash
# Start the app
streamlit run app.py

```

Check the logs for table identification:
```
[Table Fuzzy Match] Found 2 relevant tables: students, class
[Token Optimization] Loading 2/5 tables
[Generated SQL] SELECT COUNT(*) FROM students s JOIN class c ON s.class_id = c.id WHERE c.grade = 1
```

## Troubleshooting

### Table Not Identified

**Problem**: User asks about a table but it's not identified

**Solution**:
1. Check if table has table-level metadata: `SELECT * FROM schema_metadata WHERE column_name IS NULL`
2. Verify business_description is clear and relevant
3. Add more descriptive keywords to business_description

### Token Overflow

**Problem**: Still hitting token limits with large schemas

**Solution**:
1. Verify table identification is working (check logs)
2. Reduce sample_values length in metadata
3. Consider implementing column-level identification for very large tables

### LLM Generates Wrong SQL

**Problem**: Generated SQL doesn't match user intent

**Solution**:
1. Improve business_description in schema_metadata
2. Add more sample_values to clarify data format
3. Check if correct tables were identified in logs

## Project Structure

```
students-project-13/
├── app.py                       # Streamlit UI
├── query_sql.py                 # Core logic with metadata-driven SQL generation
├── schema_metadata.sql          # Database schema with metadata
├── ARCHITECTURE.md              # System architecture documentation
├── README.md                    # This file
└── requirements.txt             # Python dependencies
```

## Key Functions

### `query_sql.py`

- `get_table_summaries()`: Retrieves table names with business descriptions for fuzzy matching
- `get_schema_metadata(table_name)`: Queries detailed metadata for specific table(s)
- `format_schema_metadata_for_llm(metadata)`: Formats metadata into readable text for LLM
- `execute_query(user_prompt, sql_query)`: Universal SQL executor with security validation
- `run_function_tool_flow(prompt, model)`: Main orchestrator with three-phase workflow


---

For more information:
- [Architecture Documentation](ARCHITECTURE.md)

