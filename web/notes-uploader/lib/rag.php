<?php
/** Returns ['status' => HTTP status, 'body' => decoded JSON]. Throws RuntimeException if the RAG cannot be reached. */
function sendToRag(string $course, string $topic, string $markdown): array
{
    $context = stream_context_create(['http' => [
        'method' => 'POST',
        'header' => "Content-Type: application/json\r\nX-CS-Token: " . CS_TOKEN . "\r\n",
        'content' => json_encode(['course' => $course, 'topic' => $topic, 'markdown' => $markdown], JSON_THROW_ON_ERROR),
        'timeout' => 15,
        'ignore_errors' => true, // read the body of 4xx replies too
    ]]);
    $body = @file_get_contents(RAG_URL . '/admin/notes', false, $context);
    if ($body === false || !isset($http_response_header[0])) {
        throw new RuntimeException('RAG service unreachable');
    }
    preg_match('#^HTTP/\S+\s+(\d+)#', $http_response_header[0], $match);
    return ['status' => (int) ($match[1] ?? 0), 'body' => json_decode($body, true) ?? []];
}
