package edu.vit.cascadeshield.staff.repo;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

import edu.vit.cascadeshield.staff.model.Exam;

public interface ExamRepository extends JpaRepository<Exam, Long> {
    List<Exam> findAllByOrderByStartAtAsc();
}
