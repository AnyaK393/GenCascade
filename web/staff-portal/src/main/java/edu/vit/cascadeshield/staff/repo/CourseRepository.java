package edu.vit.cascadeshield.staff.repo;

import org.springframework.data.jpa.repository.JpaRepository;

import edu.vit.cascadeshield.staff.model.Course;

public interface CourseRepository extends JpaRepository<Course, String> {
}
