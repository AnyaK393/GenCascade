package edu.vit.cascadeshield.staff.service;

import java.net.http.HttpClient;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.Arrays;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import edu.vit.cascadeshield.staff.model.Exam;

/** Tells the resilience core about a new exam. Failure never loses the exam: it only returns false. */
@Service
public class CoreNotifier {
    private static final Logger log = LoggerFactory.getLogger(CoreNotifier.class);
    private static final Duration TIMEOUT = Duration.ofSeconds(3);
    private static final double MIN_IN_MINUTES = 0.1;
    private static final double PREWARM_MIN = 1.5;

    private final RestClient client;
    private final String token;

    public CoreNotifier(@Value("${cs.core-url}") String coreUrl, @Value("${cs.token}") String token) {
        // HTTP/1.1 only: the default h2c upgrade makes uvicorn drop the POST body (422 from the core)
        var http = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).connectTimeout(TIMEOUT).build();
        var factory = new JdkClientHttpRequestFactory(http);
        factory.setReadTimeout(TIMEOUT);
        this.client = RestClient.builder().baseUrl(coreUrl).requestFactory(factory).build();
        this.token = token;
    }

    public boolean notifyCreated(Exam exam) {
        double inMinutes = Duration.between(OffsetDateTime.now(), exam.getStartAt()).toMillis() / 60000.0;
        Map<String, Object> body = Map.of(
                "course", exam.getCourse().getCode(),
                "in_minutes", Math.max(MIN_IN_MINUTES, inMinutes),
                "duration_min", exam.getDurationMin(),
                "expected_students", exam.getExpectedStudents(),
                "topics", Arrays.asList(exam.getTopics().split(",")),
                "prewarm_min", PREWARM_MIN);
        try {
            client.post().uri("/ops/exam").header("X-CS-Token", token)
                    .contentType(MediaType.APPLICATION_JSON).body(body).retrieve().toBodilessEntity();
            return true;
        } catch (RestClientException e) {
            log.warn("resilience core not notified of exam {}: {}", exam.getId(), e.getMessage());
            return false;
        }
    }
}
