package edu.vit.cascadeshield.staff;

import org.springframework.boot.CommandLineRunner;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Component;

import edu.vit.cascadeshield.staff.model.Course;
import edu.vit.cascadeshield.staff.model.Role;
import edu.vit.cascadeshield.staff.model.StaffUser;
import edu.vit.cascadeshield.staff.repo.CourseRepository;
import edu.vit.cascadeshield.staff.repo.StaffUserRepository;

@Component
public class DataSeeder implements CommandLineRunner {
    private final CourseRepository courses;
    private final StaffUserRepository users;
    private final BCryptPasswordEncoder encoder;

    public DataSeeder(CourseRepository courses, StaffUserRepository users, BCryptPasswordEncoder encoder) {
        this.courses = courses;
        this.users = users;
        this.encoder = encoder;
    }

    @Override
    public void run(String... args) {
        seedCourse("DSA101", "Data Structures");
        seedCourse("DBMS201", "Database Systems");
        seedCourse("OS202", "Operating Systems");
        seedUser("instructor@vit.edu", "Demo Instructor", "instructor123", Role.INSTRUCTOR);
        seedUser("admin@vit.edu", "Demo Admin", "admin123", Role.ADMIN);
    }

    private void seedCourse(String code, String title) {
        if (!courses.existsById(code)) {
            courses.save(new Course(code, title));
        }
    }

    private void seedUser(String email, String name, String password, Role role) {
        if (users.findByEmail(email).isEmpty()) {
            users.save(new StaffUser(email, name, encoder.encode(password), role));
        }
    }
}
