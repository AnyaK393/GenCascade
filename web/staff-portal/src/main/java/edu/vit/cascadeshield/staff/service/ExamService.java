package edu.vit.cascadeshield.staff.service;

import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;

import edu.vit.cascadeshield.staff.model.Exam;
import edu.vit.cascadeshield.staff.repo.CourseRepository;
import edu.vit.cascadeshield.staff.repo.ExamRepository;
import jakarta.validation.Validator;

/** The form and the REST API share these rules, so both validate and notify the core the same way. */
@Service
public class ExamService {
    public record ExamInput(String course, OffsetDateTime startAt, Integer durationMin, Integer expectedStudents, String topics) {
    }

    /** errors is empty on success; coreNotified is only meaningful for a create. */
    public record Result(Exam exam, Map<String, String> errors, boolean coreNotified) {
    }

    private final ExamRepository exams;
    private final CourseRepository courses;
    private final Validator validator;
    private final CoreNotifier core;

    public ExamService(ExamRepository exams, CourseRepository courses, Validator validator, CoreNotifier core) {
        this.exams = exams;
        this.courses = courses;
        this.validator = validator;
        this.core = core;
    }

    public List<Exam> upcoming() {
        OffsetDateTime now = OffsetDateTime.now();
        return exams.findAllByOrderByStartAtAsc().stream().filter(e -> e.endAt().isAfter(now)).toList();
    }

    public Result create(ExamInput in, String createdBy) {
        Exam exam = new Exam();
        exam.setCreatedBy(createdBy);
        exam.setCreatedAt(OffsetDateTime.now());
        Map<String, String> errors = apply(exam, in);
        if (!errors.isEmpty()) {
            return new Result(exam, errors, false);
        }
        Exam saved = exams.save(exam);
        return new Result(saved, errors, core.notifyCreated(saved));
    }

    public Result update(Exam exam, ExamInput in) {
        Map<String, String> errors = apply(exam, in);
        if (!errors.isEmpty()) {
            return new Result(exam, errors, false);
        }
        return new Result(exams.save(exam), errors, false);
    }

    private Map<String, String> apply(Exam exam, ExamInput in) {
        exam.setCourse(in.course() == null ? null : courses.findById(in.course()).orElse(null));
        exam.setStartAt(in.startAt());
        exam.setDurationMin(in.durationMin());
        exam.setExpectedStudents(in.expectedStudents());
        exam.setTopics(in.topics());
        Map<String, String> errors = new LinkedHashMap<>();
        validator.validate(exam).forEach(v -> errors.putIfAbsent(v.getPropertyPath().toString(), v.getMessage()));
        return errors;
    }
}
