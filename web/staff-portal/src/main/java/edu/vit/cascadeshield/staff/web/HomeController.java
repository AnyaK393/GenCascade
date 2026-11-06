package edu.vit.cascadeshield.staff.web;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

import edu.vit.cascadeshield.staff.repo.CourseRepository;
import edu.vit.cascadeshield.staff.service.ExamService;

@Controller
public class HomeController {
    private final CourseRepository courses;
    private final ExamService exams;
    private final String statusUrl;
    private final String notesUrl;
    private final String dashboardUrl;

    public HomeController(CourseRepository courses, ExamService exams,
            @Value("${links.status}") String statusUrl,
            @Value("${links.notes}") String notesUrl,
            @Value("${links.dashboard}") String dashboardUrl) {
        this.courses = courses;
        this.exams = exams;
        this.statusUrl = statusUrl;
        this.notesUrl = notesUrl;
        this.dashboardUrl = dashboardUrl;
    }

    @GetMapping("/login")
    public String login() {
        return "login";
    }

    @GetMapping("/")
    public String home(Model model) {
        model.addAttribute("courseCount", courses.count());
        model.addAttribute("upcomingCount", exams.upcoming().size());
        model.addAttribute("statusUrl", statusUrl);
        model.addAttribute("notesUrl", notesUrl);
        model.addAttribute("dashboardUrl", dashboardUrl);
        return "home";
    }
}
