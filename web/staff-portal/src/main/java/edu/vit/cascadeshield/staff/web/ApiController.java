package edu.vit.cascadeshield.staff.web;

import java.security.Principal;
import java.time.OffsetDateTime;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import edu.vit.cascadeshield.staff.model.Course;
import edu.vit.cascadeshield.staff.model.Exam;
import edu.vit.cascadeshield.staff.repo.CourseRepository;
import edu.vit.cascadeshield.staff.repo.ExamRepository;
import edu.vit.cascadeshield.staff.service.ExamService;

/** JSON names are snake_case (spring.jackson.property-naming-strategy). */
@RestController
@RequestMapping("/api")
public class ApiController {
    public record ExamRequest(String course, OffsetDateTime start, Integer durationMin, Integer expectedStudents, List<String> topics) {
        ExamService.ExamInput toInput() {
            return new ExamService.ExamInput(course, start, durationMin, expectedStudents, topics == null ? null : String.join(",", topics));
        }
    }

    public record ExamView(long id, String course, OffsetDateTime start, int durationMin, int expectedStudents, List<String> topics) {
        static ExamView of(Exam e) {
            return new ExamView(e.getId(), e.getCourse().getCode(), e.getStartAt(), e.getDurationMin(), e.getExpectedStudents(),
                    Arrays.asList(e.getTopics().split(",")));
        }
    }

    private static final Map<String, String> JSON_NAMES = Map.of(
            "startAt", "start", "durationMin", "duration_min", "expectedStudents", "expected_students");

    private final ExamService service;
    private final ExamRepository exams;
    private final CourseRepository courses;

    public ApiController(ExamService service, ExamRepository exams, CourseRepository courses) {
        this.service = service;
        this.exams = exams;
        this.courses = courses;
    }

    @GetMapping("/courses")
    public List<Course> courses() {
        return courses.findAll();
    }

    @GetMapping("/exams")
    public List<ExamView> all() {
        return exams.findAllByOrderByStartAtAsc().stream().map(ExamView::of).toList();
    }

    @GetMapping("/exams/upcoming")
    public List<ExamView> upcoming() {
        return service.upcoming().stream().map(ExamView::of).toList();
    }

    @PostMapping("/exams")
    public ResponseEntity<?> create(@RequestBody ExamRequest body, Principal user) {
        var result = service.create(body.toInput(), user.getName());
        if (!result.errors().isEmpty()) {
            return badRequest(result.errors());
        }
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("exam", ExamView.of(result.exam()), "core_notified", result.coreNotified()));
    }

    @PutMapping("/exams/{id}")
    public ResponseEntity<?> update(@PathVariable long id, @RequestBody ExamRequest body) {
        Exam exam = exams.findById(id).orElse(null);
        if (exam == null) {
            return ResponseEntity.notFound().build();
        }
        var result = service.update(exam, body.toInput());
        if (!result.errors().isEmpty()) {
            return badRequest(result.errors());
        }
        return ResponseEntity.ok(ExamView.of(result.exam()));
    }

    @DeleteMapping("/exams/{id}")
    public ResponseEntity<Void> delete(@PathVariable long id) {
        if (!exams.existsById(id)) {
            return ResponseEntity.notFound().build();
        }
        exams.deleteById(id);
        return ResponseEntity.noContent().build();
    }

    private static ResponseEntity<Map<String, Object>> badRequest(Map<String, String> errors) {
        Map<String, String> named = new LinkedHashMap<>();
        errors.forEach((field, message) -> named.put(JSON_NAMES.getOrDefault(field, field), message));
        return ResponseEntity.badRequest().body(Map.of("errors", named));
    }
}
