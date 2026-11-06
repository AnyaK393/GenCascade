package edu.vit.cascadeshield.status;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.sql.SQLException;
import java.time.Duration;
import java.util.Date;
import java.util.Objects;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import jakarta.servlet.ServletContextEvent;
import jakarta.servlet.ServletContextListener;
import jakarta.servlet.annotation.WebListener;

/** Keeps the latest StatusBean in the servlet context and records every level change. */
@WebListener
public class StatusPoller implements ServletContextListener {
    public static final String ATTRIBUTE = "status";

    private static final Logger log = Logger.getLogger(StatusPoller.class.getName());
    private static final Duration TIMEOUT = Duration.ofSeconds(2);
    private static final String[] LEVEL_NAMES = {"Full", "Light mode", "Course notes", "Hints", "Queued"};
    private static final String UNKNOWN_LEVEL = "not recorded yet";

    private static final Pattern LEVEL = Pattern.compile("\"level\"\\s*:\\s*(\\d+)");
    private static final Pattern BANNER = Pattern.compile("\"banner\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"");
    private static final Pattern COLOR = Pattern.compile("\"color\"\\s*:\\s*\"(\\w+)\"");
    private static final Pattern EXAM = Pattern.compile("\"exam\"\\s*:\\s*\\{[^}]*\"active\"\\s*:\\s*true[^}]*\\}");
    private static final Pattern EXAM_COURSE = Pattern.compile("\"course\"\\s*:\\s*\"(\\w+)\"");
    private static final Pattern CORE_HEALTHY = Pattern.compile("\"healthy\"\\s*:\\s*true");
    private static final Pattern LLM_RISK = Pattern.compile("\"risk\"\\s*:\\s*\\{[^}]*\"llm_inference\"\\s*:\\s*([0-9.eE+-]+)");

    private final String gatewayUrl = Db.env("GATEWAY_URL", "http://localhost:8000");
    private final String coreUrl = Db.env("CORE_URL", "http://localhost:8600");
    private final HttpClient http = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).connectTimeout(TIMEOUT).build();
    private final AtomicReference<StatusBean> latest = new AtomicReference<>();
    private ScheduledExecutorService executor;
    private Object lastRecordedLevel = UNKNOWN_LEVEL;

    @Override
    public void contextInitialized(ServletContextEvent event) {
        event.getServletContext().setAttribute(ATTRIBUTE, latest);
        try {
            Db.ensureTable();
        } catch (SQLException e) {
            log.log(Level.WARNING, "status_history not ready: {0}", e.getMessage());
        }
        executor = Executors.newSingleThreadScheduledExecutor();
        // scheduleWithFixedDelay stops for good after an exception, hence the catch inside poll
        executor.scheduleWithFixedDelay(this::poll, 0, 5, TimeUnit.SECONDS);
    }

    @Override
    public void contextDestroyed(ServletContextEvent event) {
        executor.shutdownNow();
    }

    private void poll() {
        try {
            StatusBean bean = read();
            latest.set(bean);
            if (!Objects.equals(lastRecordedLevel, bean.getLevel())) {
                Db.insertHistory(bean.getLevel(), bean.getBanner(), bean.isExamActive());
                lastRecordedLevel = bean.getLevel(); // only after the insert: a DB outage retries instead of losing the change
            }
        } catch (Exception e) {
            log.log(Level.WARNING, "status poll failed: {0}", e.toString());
        }
    }

    private String get(String url) {
        try {
            HttpRequest request = HttpRequest.newBuilder(URI.create(url)).timeout(TIMEOUT).build();
            HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
            return response.statusCode() == 200 ? response.body() : null;
        } catch (java.io.IOException e) {
            return null;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return null;
        }
    }

    private static String first(Pattern pattern, String text) {
        Matcher m = pattern.matcher(text);
        return m.find() ? m.group(1) : null;
    }

    // shortcut: regexes over two small, fixed JSON shapes (no JSON library in the plan), use a parser if they ever nest deeper
    static StatusBean parse(String gateway, String core) {
        StatusBean bean = new StatusBean();
        bean.setCheckedAt(new Date());
        if (gateway == null) {
            bean.setLevelName("Unknown");
            bean.setBanner("The student platform is not responding.");
            bean.setColor("red");
        } else {
            String level = first(LEVEL, gateway);
            bean.setLevel(level == null ? null : Integer.valueOf(level));
            bean.setLevelName(bean.getLevel() != null && bean.getLevel() < LEVEL_NAMES.length ? LEVEL_NAMES[bean.getLevel()] : "Unknown");
            bean.setBanner(first(BANNER, gateway));
            bean.setColor(first(COLOR, gateway));
            Matcher exam = EXAM.matcher(gateway);
            if (exam.find()) {
                bean.setExamActive(true);
                bean.setExamCourse(first(EXAM_COURSE, exam.group()));
            }
        }
        bean.setCoreHealthy(core != null && CORE_HEALTHY.matcher(core).find());
        if (core != null) {
            String risk = first(LLM_RISK, core);
            bean.setRisk(risk == null ? null : Double.valueOf(risk));
        }
        return bean;
    }

    private StatusBean read() {
        return parse(get(gatewayUrl + "/api/status"), get(coreUrl + "/state"));
    }
}
