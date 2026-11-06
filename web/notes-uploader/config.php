<?php
// All settings come from the environment, so nothing secret is stored in this folder.
function env_or(string $name, string $default): string
{
    $value = getenv($name);
    return $value === false || $value === '' ? $default : $value;
}

define('MYSQL_HOST', env_or('MYSQL_HOST', 'localhost'));
define('MYSQL_DB', env_or('MYSQL_DB', 'cascadeshield_web'));
define('MYSQL_USER', env_or('MYSQL_USER', 'csweb'));
define('MYSQL_PASSWORD', env_or('MYSQL_PASSWORD', ''));
define('RAG_URL', rtrim(env_or('RAG_URL', 'http://localhost:8003'), '/'));
define('CS_TOKEN', env_or('CS_TOKEN', 'dev-token'));

define('COURSES', ['DSA101', 'DBMS201', 'OS202']);
define('MAX_BYTES', 200 * 1024);
define('MIN_MARKDOWN', 20);       // these two match POST /admin/notes in the RAG service
define('MAX_MARKDOWN', 100000);
define('UPLOADS_DIR', __DIR__ . '/uploads');
define('OUTBOX_DIR', __DIR__ . '/outbox');
