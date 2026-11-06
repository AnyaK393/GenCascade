<?php
function db(): PDO
{
    static $pdo = null;
    if ($pdo === null) {
        $dsn = 'mysql:host=' . MYSQL_HOST . ';dbname=' . MYSQL_DB . ';charset=utf8mb4';
        $pdo = new PDO($dsn, MYSQL_USER, MYSQL_PASSWORD, [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_TIMEOUT => 3,
        ]);
    }
    return $pdo;
}

function find_staff(string $email): ?array
{
    $stmt = db()->prepare('SELECT email, name, password_hash FROM staff_user WHERE email = ?');
    $stmt->execute([$email]);
    return $stmt->fetch() ?: null;
}

function record_upload(string $course, string $topic, string $filename, string $by, string $status, ?int $chunks): void
{
    $stmt = db()->prepare('INSERT INTO note_upload (course, topic, filename, uploaded_by, status, chunks) VALUES (?, ?, ?, ?, ?, ?)');
    $stmt->execute([$course, $topic, $filename, $by, $status, $chunks]);
}

function recent_uploads(): array
{
    return db()->query('SELECT * FROM note_upload ORDER BY id DESC LIMIT 20')->fetchAll();
}
