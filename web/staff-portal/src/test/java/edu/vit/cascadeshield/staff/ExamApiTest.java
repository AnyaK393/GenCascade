package edu.vit.cascadeshield.staff;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.OffsetDateTime;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

// Port 1 refuses connections, so "exam saved although the core is down" is tested too.
@SpringBootTest(properties = "cs.core-url=http://localhost:1")
@AutoConfigureMockMvc
class ExamApiTest {
    @Autowired
    MockMvc mvc;

    private static String body(int durationMin) {
        return """
                {"course":"DSA101","start":"%s","duration_min":%d,"expected_students":100,"topics":["bst","heaps"]}
                """.formatted(OffsetDateTime.now().plusHours(1), durationMin);
    }

    @Test
    void upcomingIsPublic() throws Exception {
        mvc.perform(get("/api/exams/upcoming")).andExpect(status().isOk());
    }

    @Test
    void postWithoutAuthIs401() throws Exception {
        mvc.perform(post("/api/exams").contentType(MediaType.APPLICATION_JSON).content(body(60)))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validPostAsInstructorIs201EvenWhenCoreIsDown() throws Exception {
        mvc.perform(post("/api/exams").with(httpBasic("instructor@vit.edu", "instructor123"))
                        .contentType(MediaType.APPLICATION_JSON).content(body(60)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.exam.course").value("DSA101"))
                .andExpect(jsonPath("$.core_notified").value(false));
    }

    @Test
    void invalidBodyIs400WithFieldErrors() throws Exception {
        mvc.perform(post("/api/exams").with(httpBasic("instructor@vit.edu", "instructor123"))
                        .contentType(MediaType.APPLICATION_JSON).content(body(1)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors.duration_min").exists());
    }
}
