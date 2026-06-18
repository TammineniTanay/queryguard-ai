DROP TABLE IF EXISTS patients;
DROP TABLE IF EXISTS departments;
DROP TABLE IF EXISTS claims;

CREATE TABLE patients (
  patient_id TEXT PRIMARY KEY,
  patient_name TEXT NOT NULL,
  email TEXT NOT NULL,
  region TEXT NOT NULL,
  birth_year INTEGER NOT NULL
);

CREATE TABLE departments (
  department_id TEXT PRIMARY KEY,
  department_name TEXT NOT NULL,
  cost_center TEXT NOT NULL,
  director TEXT NOT NULL
);

CREATE TABLE claims (
  claim_id TEXT PRIMARY KEY,
  patient_id TEXT NOT NULL,
  department_id TEXT NOT NULL,
  diagnosis_code TEXT NOT NULL,
  claim_amount REAL NOT NULL,
  status TEXT NOT NULL,
  claim_date TEXT NOT NULL,
  FOREIGN KEY(patient_id) REFERENCES patients(patient_id),
  FOREIGN KEY(department_id) REFERENCES departments(department_id)
);

INSERT INTO patients VALUES
('P001', 'Maya Johnson', 'maya@example.com', 'South', 1982),
('P002', 'Ethan Brown', 'ethan@example.com', 'East', 1975),
('P003', 'Sophia Davis', 'sophia@example.com', 'West', 1991),
('P004', 'Liam Wilson', 'liam@example.com', 'South', 1968),
('P005', 'Olivia Martin', 'olivia@example.com', 'North', 1988),
('P006', 'Noah Garcia', 'noah@example.com', 'East', 1979);

INSERT INTO departments VALUES
('D10', 'Cardiology', 'CC-9001', 'Dr. Aria Patel'),
('D20', 'Radiology', 'CC-9002', 'Dr. Ken Miller'),
('D30', 'Oncology', 'CC-9003', 'Dr. Nina Shah'),
('D40', 'Emergency', 'CC-9004', 'Dr. Omar Lee');

INSERT INTO claims VALUES
('C1001', 'P001', 'D10', 'I25.10', 1250.00, 'approved', '2025-01-12'),
('C1002', 'P001', 'D20', 'R93.1', 640.50, 'approved', '2025-01-18'),
('C1003', 'P002', 'D10', 'I10', 810.00, 'denied', '2025-02-02'),
('C1004', 'P003', 'D30', 'C50.9', 4400.00, 'approved', '2025-02-17'),
('C1005', 'P004', 'D40', 'S09.90', 980.25, 'pending', '2025-03-04'),
('C1006', 'P005', 'D30', 'C34.90', 5200.00, 'denied', '2025-03-08'),
('C1007', 'P006', 'D20', 'R07.9', 700.00, 'approved', '2025-03-20'),
('C1008', 'P002', 'D40', 'R51.9', 450.75, 'approved', '2025-04-11'),
('C1009', 'P003', 'D10', 'I48.91', 1500.00, 'approved', '2025-04-19'),
('C1010', 'P004', 'D20', 'R93.89', 875.00, 'denied', '2025-05-05'),
('C1011', 'P005', 'D10', 'I20.9', 1320.00, 'approved', '2025-05-09'),
('C1012', 'P006', 'D40', 'S01.81', 610.00, 'approved', '2025-05-17');
