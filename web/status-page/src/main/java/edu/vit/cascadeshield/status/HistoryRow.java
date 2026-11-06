package edu.vit.cascadeshield.status;

import java.util.Date;

/** One row of status_history; a JavaBean because JSTL reads it through getters. */
public class HistoryRow {
    private final Integer level;
    private final String banner;
    private final boolean examActive;
    private final Date changedAt;

    public HistoryRow(Integer level, String banner, boolean examActive, Date changedAt) {
        this.level = level;
        this.banner = banner;
        this.examActive = examActive;
        this.changedAt = changedAt;
    }

    public Integer getLevel() {
        return level;
    }

    public String getBanner() {
        return banner;
    }

    public boolean isExamActive() {
        return examActive;
    }

    public Date getChangedAt() {
        return changedAt;
    }

    /** Percent of the last 24 h at level 0-1, or null with no data. rowsNewestFirst may start before the window. */
    public static Double healthyShare(java.util.List<HistoryRow> rowsNewestFirst, long nowMillis) {
        long windowStart = nowMillis - 24 * 3600 * 1000L;
        long segmentEnd = nowMillis;
        long total = 0;
        long healthy = 0;
        for (HistoryRow row : rowsNewestFirst) {
            long segmentStart = Math.max(row.changedAt.getTime(), windowStart);
            long span = Math.max(0, segmentEnd - segmentStart);
            total += span;
            if (row.level != null && row.level <= 1) {
                healthy += span;
            }
            segmentEnd = segmentStart;
            if (segmentStart == windowStart) {
                break;
            }
        }
        return total == 0 ? null : 100.0 * healthy / total;
    }
}
