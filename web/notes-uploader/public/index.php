<?php
require __DIR__ . '/../config.php';
require __DIR__ . '/../lib/db.php';
require __DIR__ . '/../lib/auth.php';

require_login();

function format_size(int $bytes): string
{
    return $bytes < 1024 ? "$bytes B" : number_format($bytes / 1024, 1) . ' KB';
}

function upload_row(array $row): array
{
    $path = UPLOADS_DIR . '/' . $row['course'] . '/' . $row['filename'];
    $row['size'] = is_file($path) ? format_size(filesize($path)) : '-';
    $row['time'] = date('d M Y H:i', strtotime($row['uploaded_at']));
    $row['status'] = ucfirst($row['status']);
    $row['topic'] = str_replace('_', ' ', $row['topic']);
    return $row;
}

$flash = flash();
$old = $_SESSION['old'] ?? ['course' => '', 'topic' => '', 'notify' => '', 'markdown' => ''];
unset($_SESSION['old']);

try {
    $uploads = array_map('upload_row', recent_uploads());
    $historyError = false;
} catch (PDOException $ex) {
    error_log($ex->getMessage());
    $uploads = [];
    $historyError = true;
}
?>
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Course notes uploader</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
<nav>
  <strong>Notes uploader</strong>
  <span><?= e($_SESSION['name']) ?></span>
  <form method="post" action="logout.php">
    <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
    <button class="link">Log out</button>
  </form>
</nav>
<main>
  <h1>Upload course notes</h1>
  <?php if ($flash): ?>
    <div class="notice <?= e($flash['type']) ?>">
      <?php foreach ($flash['lines'] as $line): ?><p><?= e($line) ?></p><?php endforeach; ?>
    </div>
  <?php endif; ?>

  <form method="post" action="upload.php" enctype="multipart/form-data" class="stack">
    <input type="hidden" name="csrf" value="<?= e(csrf_token()) ?>">
    <label>Course
      <select name="course">
        <?php foreach (COURSES as $course): ?>
          <option <?= $old['course'] === $course ? 'selected' : '' ?>><?= e($course) ?></option>
        <?php endforeach; ?>
      </select>
    </label>
    <label>Topic slug <input name="topic" value="<?= e($old['topic']) ?>" placeholder="tries"></label>
    <label>File (.md or .txt, up to 200 KB) <input type="file" name="file" accept=".md,.txt"></label>
    <label>Or paste Markdown <textarea name="markdown" rows="8" placeholder="## Concept"><?= e($old['markdown']) ?></textarea></label>
    <label>Notify e-mail (optional) <input type="text" name="notify" value="<?= e($old['notify']) ?>"></label>
    <button>Upload</button>
  </form>

  <h2>Recent uploads</h2>
  <?php if ($historyError): ?>
    <p>The upload history is unavailable right now.</p>
  <?php elseif (!$uploads): ?>
    <p>Nothing uploaded yet.</p>
  <?php else: ?>
    <div class="scroll">
      <table>
        <thead><tr><th>Course</th><th>Topic</th><th>Uploader</th><th>Time</th><th>Size</th><th>Status</th><th>Chunks</th></tr></thead>
        <tbody>
          <?php foreach ($uploads as $row): ?>
            <tr>
              <td><?= e($row['course']) ?></td>
              <td><?= e($row['topic']) ?></td>
              <td><?= e($row['uploaded_by']) ?></td>
              <td><?= e($row['time']) ?></td>
              <td><?= e($row['size']) ?></td>
              <td><?= e($row['status']) ?></td>
              <td><?= e($row['chunks'] === null ? '-' : (string) $row['chunks']) ?></td>
            </tr>
          <?php endforeach; ?>
        </tbody>
      </table>
    </div>
  <?php endif; ?>
</main>
</body>
</html>
