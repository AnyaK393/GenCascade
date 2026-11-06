package edu.vit.cascadeshield.staff;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

import edu.vit.cascadeshield.staff.repo.StaffUserRepository;

@Configuration
public class SecurityConfig {
    private static final String[] STAFF = {"INSTRUCTOR", "ADMIN"};

    /** Exact type on purpose: stores plain $2a$ hashes that PHP's password_verify() can read. */
    @Bean
    BCryptPasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(StaffUserRepository users) {
        return email -> users.findByEmail(email)
                .map(u -> User.withUsername(u.getEmail()).password(u.getPasswordHash()).roles(u.getRole().name()).build())
                .orElseThrow(() -> new UsernameNotFoundException(email));
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http.securityMatcher("/api/**")
                .csrf(csrf -> csrf.disable())
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(Customizer.withDefaults())
                .authorizeHttpRequests(a -> a
                        .requestMatchers(HttpMethod.GET, "/api/exams/upcoming").permitAll()
                        .anyRequest().hasAnyRole(STAFF))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
                .formLogin(f -> f.loginPage("/login").defaultSuccessUrl("/", true).permitAll())
                .logout(l -> l.logoutSuccessUrl("/login?logout").permitAll())
                .authorizeHttpRequests(a -> a
                        .requestMatchers("/css/**", "/error").permitAll()
                        .requestMatchers("/actuator/health").permitAll()
                        .requestMatchers("/actuator/**", "/admin/**").hasRole("ADMIN")
                        .requestMatchers("/exams/**").hasAnyRole(STAFF)
                        .anyRequest().authenticated())
                .build();
    }
}
