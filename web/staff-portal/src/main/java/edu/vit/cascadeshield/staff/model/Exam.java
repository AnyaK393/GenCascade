package edu.vit.cascadeshield.staff.model;

import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToOne;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

@Entity
public class Exam {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotNull(message = "Choose a course")
    @ManyToOne(optional = false)
    private Course course;

    @NotNull(message = "Enter a start time")
    @Future(message = "Start must be in the future")
    @Column(nullable = false)
    private OffsetDateTime startAt;

    @NotNull(message = "Enter a duration")
    @Min(value = 5, message = "Duration must be 5-240 minutes")
    @Max(value = 240, message = "Duration must be 5-240 minutes")
    @Column(nullable = false)
    private Integer durationMin;

    @NotNull(message = "Enter the expected students")
    @Min(value = 1, message = "Expected students must be 1-2000")
    @Max(value = 2000, message = "Expected students must be 1-2000")
    @Column(nullable = false)
    private Integer expectedStudents;

    @NotNull(message = "Enter the topics")
    @Pattern(regexp = "^[a-z0-9_]+(,[a-z0-9_]+)*$", message = "Topics must be lowercase and comma-separated, like bst,heaps")
    @Column(nullable = false)
    private String topics;

    @Column(nullable = false)
    private String createdBy;

    @Column(nullable = false)
    private OffsetDateTime createdAt;

    public OffsetDateTime endAt() {
        return startAt.plusMinutes(durationMin);
    }

    /** Stored in UTC; shown in the server's own zone. */
    public ZonedDateTime getLocalStart() {
        return startAt.atZoneSameInstant(ZoneId.systemDefault());
    }

    public Long getId() {
        return id;
    }

    public Course getCourse() {
        return course;
    }

    public void setCourse(Course course) {
        this.course = course;
    }

    public OffsetDateTime getStartAt() {
        return startAt;
    }

    public void setStartAt(OffsetDateTime startAt) {
        this.startAt = startAt;
    }

    public Integer getDurationMin() {
        return durationMin;
    }

    public void setDurationMin(Integer durationMin) {
        this.durationMin = durationMin;
    }

    public Integer getExpectedStudents() {
        return expectedStudents;
    }

    public void setExpectedStudents(Integer expectedStudents) {
        this.expectedStudents = expectedStudents;
    }

    public String getTopics() {
        return topics;
    }

    public void setTopics(String topics) {
        this.topics = topics;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public void setCreatedBy(String createdBy) {
        this.createdBy = createdBy;
    }

    public OffsetDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(OffsetDateTime createdAt) {
        this.createdAt = createdAt;
    }
}
