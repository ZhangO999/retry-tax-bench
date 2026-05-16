SELECT COUNT(*) AS account_count FROM Account;
SELECT COUNT(*) AS savings_count FROM Savings;
SELECT COUNT(*) AS checking_count FROM Checking;
SELECT COALESCE(SUM(Balance), 0) AS savings_total FROM Savings;
SELECT COALESCE(SUM(Balance), 0) AS checking_total FROM Checking;
SELECT COALESCE((SELECT SUM(Balance) FROM Savings), 0)
     + COALESCE((SELECT SUM(Balance) FROM Checking), 0) AS total_funds;
