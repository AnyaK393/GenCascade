package edu.vit.cascadeshield.status;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Date;
import java.util.List;

import org.junit.jupiter.api.Test;

class StatusLogicTest {
    private static final long HOUR = 3600 * 1000L;
    private static final long NOW = 1000 * HOUR;

    private static HistoryRow row(Integer level, long hoursAgo) {
        return new HistoryRow(level, "b", false, new Date(NOW - hoursAgo * HOUR));
    }

    @Test
    void noHistoryHasNoShare() {
        assertNull(HistoryRow.healthyShare(List.of(), NOW));
    }

    @Test
    void shareWeighsTimeAtEachLevel() {
        // level 3 for the last 6 h, level 0 for the 6 h before: half healthy
        assertEquals(50.0, HistoryRow.healthyShare(List.of(row(3, 6), row(0, 12)), NOW), 0.001);
    }

    @Test
    void rowsBeforeTheWindowCountOnlyInsideIt() {
        // level 0 began 100 h ago and level 2 took over 12 h ago: 12 of the last 24 h were healthy
        assertEquals(50.0, HistoryRow.healthyShare(List.of(row(2, 12), row(0, 100), row(4, 200)), NOW), 0.001);
    }

    @Test
    void unreachableIsNotHealthy() {
        assertEquals(0.0, HistoryRow.healthyShare(List.of(row(null, 1)), NOW), 0.001);
    }

    @Test
    void parsesLiveResponses() {
        String gateway = "{\"level\":2,\"banner\":\"High demand: \\\"notes\\\"\",\"color\":\"blue\",\"exam\":{\"active\":true,\"course\":\"DSA101\",\"ends_at\":null}}";
        String core = "{\"healthy\":true,\"risk\":{\"gateway\":null,\"llm_inference\":0.42}}";
        StatusBean bean = StatusPoller.parse(gateway, core);
        assertEquals(2, bean.getLevel());
        assertEquals("Course notes", bean.getLevelName());
        assertTrue(bean.isExamActive());
        assertEquals("DSA101", bean.getExamCourse());
        assertTrue(bean.isCoreHealthy());
        assertEquals(0.42, bean.getRisk(), 0.001);
    }

    @Test
    void examOffAndBackendsDown() {
        assertFalse(StatusPoller.parse("{\"level\":0,\"banner\":\"ok\",\"color\":\"green\",\"exam\":{\"active\":false}}", null).isExamActive());
        StatusBean down = StatusPoller.parse(null, null);
        assertNull(down.getLevel());
        assertFalse(down.isCoreHealthy());
    }
}
