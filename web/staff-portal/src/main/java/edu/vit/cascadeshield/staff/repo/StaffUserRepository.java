package edu.vit.cascadeshield.staff.repo;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

import edu.vit.cascadeshield.staff.model.StaffUser;

public interface StaffUserRepository extends JpaRepository<StaffUser, Long> {
    Optional<StaffUser> findByEmail(String email);
}
