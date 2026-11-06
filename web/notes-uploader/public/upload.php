<?php
require __DIR__ . '/../config.php';
require __DIR__ . '/../lib/db.php';
require __DIR__ . '/../lib/auth.php';
require __DIR__ . '/../lib/rag.php';

require_login();
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    header('Location: index.php');
    exit;
}
check_csrf();

$course = $_POST['course'] ?? '';
$topic = trim($_POST['topic'] ?? '');
$pasted = trim($_POST['markdown'] ?? '');
$notify = trim($_POST['notify'] ?? '');
$file = $_FILES['file'] ?? null;
$hasFile = $file !== null && $file['error'] !== UPLOAD_ERR_NO_FILE;
$errors = [];
$markdown = '';

if (!in_array($course, COURSES, true)) {
    $errors[] = 'Choose a course from the list.';
}
if (!preg_match('/^[a-z0-9_]{2,40}$/D', $topic)) {
    $errors[] = 'Topic must be 2-40 characters: lowercase letters, digits and underscores.';
}
if ($notify !== '' && !filter_var($notify, FILTER_VALIDATE_EMAIL)) {
    $errors[] = 'The notify address is not a valid e-mail.';
}

if ($hasFile && $pasted !== '') {
    $errors[] = 'Upload a file or paste Markdown, not both.';
} elseif ($hasFile) {
    $extension = strtolower(pathinfo($file['name'], PATHINFO_EXTENSION));
    if ($file['error'] === UPLOAD_ERR_INI_SIZE || $file['error'] === UPLOAD_ERR_FORM_SIZE || $file['size'] > MAX_BYTES) {
        $errors[] = 'The file must be 200 KB or smaller.';
    } elseif ($file['error'] !== UPLOAD_ERR_OK) {
        $errors[] = 'The upload did not finish. Try again.';
    } else {
        if (!in_array($extension, ['md', 'txt'], true)) {
            $errors[] = 'Only .md and .txt files are accepted.';
        }
        $mime = (new finfo(FILEINFO_MIME_TYPE))->file($file['tmp_name']);
        if (!in_array($mime, ['text/plain', 'text/markdown'], true)) {
            $errors[] = 'The file is not a text file.';
        }
        $markdown = (string) file_get_contents($file['tmp_name']);
    }
} elseif ($pasted !== '') {
    $markdown = $pasted;
} else {
    $errors[] = 'Choose a file or paste some Markdown.';
}

if ($markdown !== '') {
    if (!preg_match('//u', $markdown)) {
        $errors[] = 'The text must be UTF-8.';
    }
    if (strlen($markdown) < MIN_MARKDOWN || strlen($markdown) > MAX_MARKDOWN) {
        $errors[] = 'The text must be between 20 and 100 000 characters.';
    }
    if (!preg_match('/^## /m', $markdown)) {
        $errors[] = 'The text needs at least one "## " heading.';
    }
}

if ($errors) {
    $_SESSION['old'] = compact('course', 'topic', 'notify') + ['markdown' => $pasted];
    flash(['type' => 'warn', 'lines' => $errors]);
    header('Location: index.php');
    exit;
}

$folder = UPLOADS_DIR . '/' . $course;
if (!is_dir($folder)) {
    mkdir($folder, 0775, true);
}
$filename = $topic . '-' . time() . '.md';
$saved = $hasFile
    ? move_uploaded_file($file['tmp_name'], "$folder/$filename")
    : file_put_contents("$folder/$filename", $markdown) !== false;
if (!$saved) {
    flash(['type' => 'warn', 'lines' => ['The file could not be saved. Nothing was uploaded.']]);
    header('Location: index.php');
    exit;
}

$chunks = null;
try {
    $reply = sendToRag($course, $topic, $markdown);
    if ($reply['status'] === 200) {
        $status = 'indexed';
        $chunks = (int) $reply['body']['chunks'];
        $unit = $chunks === 1 ? 'chunk' : 'chunks';
        $message = ['type' => 'ok', 'lines' => ["Indexed, $chunks $unit. The tutor can use these notes now."]];
    } elseif ($reply['status'] >= 400 && $reply['status'] < 500) {
        $status = 'failed';
        $detail = $reply['body']['detail'] ?? '';
        $reason = is_string($detail) ? $detail : 'the notes were rejected';
        $message = ['type' => 'warn', 'lines' => ["The tutor service refused these notes: $reason. The file is kept."]];
    } else {
        throw new RuntimeException('RAG returned ' . $reply['status']);
    }
} catch (RuntimeException $ex) {
    error_log($ex->getMessage());
    $status = 'pending';
    $message = ['type' => 'warn', 'lines' => ['The tutor service is unreachable. The file is saved as pending and is not searchable yet.']];
}

try {
    record_upload($course, $topic, $filename, $_SESSION['email'], $status, $chunks);
} catch (PDOException $ex) {
    error_log($ex->getMessage());
    $message['type'] = 'warn';
    $message['lines'][] = 'The upload could not be added to the history table.';
}

if ($notify !== '' && $status === 'indexed') {
    if (!is_dir(OUTBOX_DIR)) {
        mkdir(OUTBOX_DIR, 0775, true);
    }
    $mail = "To: $notify\r\nFrom: notes@cascadeshield.local\r\nSubject: New notes for $course: $topic\r\n\r\n"
        . "{$_SESSION['name']} uploaded new notes for $course on the topic \"$topic\".\r\n";
    file_put_contents(OUTBOX_DIR . '/' . $course . '-' . $topic . '-' . time() . '.eml', $mail);
    $message['lines'][] = "Notification written to the outbox for $notify.";
}

flash($message);
header('Location: index.php');
