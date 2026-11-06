package edu.vit.cascadeshield.status;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Timestamp;
import java.sql.Types;
import java.util.ArrayList;
import java.util.List;

public final class Db {
    private static final String URL = env("STATUS_DB_URL", "jdbc:mysql://localhost:3306/cascadeshield_web");
    private static final String USER = env("MYSQL_USER", "csweb");
    private static final String PASSWORD = env("MYSQL_PASSWORD", "");

    static {
        try {
            // DriverManager does not see drivers inside a WAR by itself under Tomcat
            Class.forName("com.mysql.cj.jdbc.Driver");
            Class.forName("org.h2.Driver");
        } catch (ClassNotFoundException e) {
            throw new IllegalStateException(e);
        }
    }

    private Db() {
    }

    static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }

    private static Connection connect() throws SQLException {
        return DriverManager.getConnection(URL, USER, PASSWORD);
    }

    /** Same table as web/sql/schema.sql, so the dev profile on H2 needs no setup. */
    public static void ensureTable() throws SQLException {
        try (Connection c = connect(); Statement s = c.createStatement()) {
            s.execute("""
                    CREATE TABLE IF NOT EXISTS status_history (
                      id BIGINT AUTO_INCREMENT PRIMARY KEY,
                      level INT NULL,
                      banner VARCHAR(200) NOT NULL,
                      exam_active BOOLEAN NOT NULL,
                      changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )""");
        }
    }

    public static void insertHistory(Integer level, String banner, boolean examActive) throws SQLException {
        String sql = "INSERT INTO status_history (level, banner, exam_active) VALUES (?, ?, ?)";
        try (Connection c = connect(); PreparedStatement p = c.prepareStatement(sql)) {
            if (level == null) {
                p.setNull(1, Types.INTEGER);
            } else {
                p.setInt(1, level);
            }
            p.setString(2, banner);
            p.setBoolean(3, examActive);
            p.executeUpdate();
        }
    }

    public static List<HistoryRow> recentHistory(int limit) throws SQLException {
        String sql = "SELECT level, banner, exam_active, changed_at FROM status_history ORDER BY id DESC LIMIT ?";
        List<HistoryRow> rows = new ArrayList<>();
        try (Connection c = connect(); PreparedStatement p = c.prepareStatement(sql)) {
            p.setInt(1, limit);
            try (ResultSet r = p.executeQuery()) {
                while (r.next()) {
                    Integer level = (Integer) r.getObject("level");
                    Timestamp at = r.getTimestamp("changed_at");
                    rows.add(new HistoryRow(level, r.getString("banner"), r.getBoolean("exam_active"), at));
                }
            }
        }
        return rows;
    }
}
