#!/usr/bin/perl
use warnings;
use strict;
use CGI;
use DBI;
use Mail::Sendmail;
use URI::Escape;
use HTML::Template;
use Archive::Zip;
use CGI::Carp qw(fatalsToBrowser);
use FindBin qw ($Bin);

my $q = CGI->new();
chdir "$Bin/../../templates" or die "Can't move to templates directory: $!";

#my $dbh = DBI->connect("DBI:mysql:database=Helpdesk;host=bilin2.babraham.ac.uk","cgiadmin","",{RaiseError=>0,AutoCommit=>1});

my $dbh = DBI->connect("DBI:mysql:database=Helpdesk;host=localhost","cgiadmin","",{RaiseError=>0,AutoCommit=>1});



unless ($dbh) {
  print_bug("Couldn't connect to database: ".$DBI::errstr);
  exit;
}

my ($user_id) = get_user_id();

exit unless (defined $user_id);

my $login_name = get_name($user_id);

my $action = $q -> param('action');

if ($action) {

  if ($action eq 'assign') {
    change_assignment();
  } elsif ($action eq 'reopen_job') {
    reopen_job();
  } elsif ($action eq 'show_job') {
    show_job();
  } elsif ($action eq 'save_job') {
    save_job();
  } elsif ($action eq 'new_job') {
    start_new_job();
  } elsif ($action eq 'complete_new_job') {
    complete_new_job();
  } elsif ($action eq 'close_job') {
    close_job();
  } elsif ($action eq 'new_job_with_details') {
    new_job_with_details();
  } elsif ($action eq 'add_note') {
    start_add_note();
  } elsif ($action eq 'Add more files') {
    start_add_note();
  } elsif ($action eq 'Add note') {
    finish_add_note();
  } elsif ($action eq 'show_cc') {
    show_cc();
  } elsif ($action eq 'add_cc') {
    add_cc();
  } elsif ($action eq 'remove_cc') {
    remove_cc();
  } elsif ($action eq 'send_file') {
    send_file();
  } elsif ($action eq 'show_person') {
    show_person();
  } elsif ($action eq 'update_person') {
    update_person();
  } elsif ($action eq 'search') {
    show_search_form();
  } elsif ($action eq 'run_search') {
    run_search();
  } else {
    print_bug("Unknown action \"$action\" called");
  }
} else {
  show_jobs();
}

$dbh -> disconnect();



############# SUBS #####################################################


sub print_bug {

  # This prints up an error message on the occasions
  # where someone has managed to do something they
  # should never normally be able to do.  This either
  # means it's a bug, or they're trying to hack the
  # script.

  my ($bug_message) = @_;

  # Let's make sure something goes into the logs so
  # this bug doesn't go unnoticed

  warn $bug_message;

  my $template = HTML::Template->new(filename=>'admin_bug.html');
  $template->param(MESSAGE => $bug_message);
  $template ->param(LOGIN_NAME => $login_name);
  print $template->output();

}

sub print_error {

  # This prints up an error message when it
  # looks like someone has made a user mistake
  # These messages could occur commonly 
  # within the normal running of the script

  my ($error_message) = @_;

  my $template = HTML::Template-> new(filename=>'admin_error.html');

  $template->param(MESSAGE => $error_message);
  $template ->param(LOGIN_NAME => $login_name);
  print $template->output();

}


sub get_user_id {

  # Translates a username to a database user id

  my $username = $q -> remote_user;

  unless ($username) {
    print_bug ("Noone appears to be logged in");
    return;
  }

  my ($id) = $dbh -> selectrow_array("SELECT id FROM Person WHERE username=?",undef,$username);

  unless ($id) {
    print_bug ("Couldn't get user id for $username: ".$dbh->errstr());
    return;
  }

  return($id);

}

sub show_jobs {

  my $template = HTML::Template->new(filename=>'admin_job_list.html');
  $template->param(LOGIN_NAME=>$login_name);

  show_unallocated_jobs($template);
  show_open_jobs($template);

  print $template->output();

}


sub show_unallocated_jobs {

  my ($template) = @_;

  # Puts out a table of unallocated jobs

  # First a little counter to see if we need to put out
  # anything at all!

  my ($count) = $dbh -> selectrow_array("SELECT count(*) FROM Job WHERE assigned_person_id IS NULL");

  unless($count) {
    return;
  }

  my @jobs;

  my $unallocated_jobs_sth = $dbh -> prepare("SELECT Job.id,Job.title,Job.commercial,Person.first_name,Person.last_name FROM Job,Person WHERE Job.assigned_person_id IS NULL AND Job.person_id=Person.id ORDER BY Job.date_opened DESC");
  $unallocated_jobs_sth -> execute() or do{print_bug ($dbh->errstr());return()};

  # We need to make up a list of people who
  # we can assign jobs to.

  my @assign_list;

  my $users_sth = $dbh -> prepare("SELECT first_name,last_name,id FROM Person WHERE can_assign_to='yes' ORDER BY last_name");
  $users_sth -> execute() or do{print_bug($dbh->errstr());return};

  while (my ($first,$last,$id) = $users_sth -> fetchrow_array()) {
    push @assign_list, {ID=>$id,
			FIRST => $first,
			LAST => $last,
		       };
  }


  while (my ($id,$title,$commercial,$first,$last) = $unallocated_jobs_sth -> fetchrow_array()) {

    push @jobs, {
		 JOB_ID => $id,
		 TITLE => modifyHTML($title),
		 COMMERCIAL => $commercial,
		 ASSIGN_TO => \@assign_list,
		 FIRST => $first,
		 LAST => $last,
		};

  }

  $template->param(UNALLOCATED => \@jobs);

}


sub show_open_jobs {

  my ($template) = @_;

  # Puts out a table of jobs which are open and assigned
  # to whoever is logged in

  # First a little counter to see if we need to put out
  # anything at all!

  my ($count) = $dbh -> selectrow_array("SELECT count(*) FROM Job WHERE assigned_person_id=$user_id AND status='open'");

  unless($count) {
    return;
  }

  my $open_jobs_sth = $dbh -> prepare("SELECT Job.id,Job.title,Job.commercial,Person.first_name,Person.last_name FROM Job,Person WHERE Job.assigned_person_id=$user_id AND Job.status='open' AND Job.person_id=Person.id ORDER BY Job.date_opened");
  $open_jobs_sth -> execute() or do{print_bug ($dbh->errstr());return()};

  my @jobs;

  while (my ($id,$title,$commercial,$first,$last) = $open_jobs_sth -> fetchrow_array()) {
    push @jobs, {
		 TITLE => modifyHTML($title),
		 FIRST => $first,
		 LAST => $last,
		 ID => $id,
		 COMMERCIAL => $commercial,
		};
  }

  $template -> param(ALLOCATED => \@jobs);

}

sub change_assignment {

  # Changes the assingment of a job

  # First let's check we've got the info
  # we need.

  my $job_id = $q -> param('job_id');

  my $assign_to = $q -> param('assign_to');


  # First let's check we've got permission to
  # change the assignment.  Anyone can make
  # the inital assignment, but from then on
  # only the current job owner can change it.

  # We'll also retrieve the current timestamp so
  # that when we do the update it doesn't get
  # squashed.

  my ($retrieved_job_id,$current_owner) = $dbh -> selectrow_array("SELECT id,assigned_person_id FROM Job WHERE id=?",undef,$job_id);

  unless ($retrieved_job_id) {
    print_bug ("Couldn't locate job with ID '$job_id'");
    return;
  }

  if ($current_owner and ($current_owner != $user_id)) {
    print_error ("Only the current job owner can chage the job assignment");
    return;
  }

  # Now let's check that we have someone to assign to:

  unless ($assign_to) {

    # If noone is specified then put out a quick form
    # asking them who to assign it to...

    my @people;

    my $users_sth = $dbh -> prepare("SELECT first_name,last_name,id FROM Person WHERE can_assign_to='yes' ORDER BY last_name");
    $users_sth -> execute() or do{print_bug($dbh->errstr());return};

    while (my ($first,$last,$id) = $users_sth -> fetchrow_array()) {

      push @people, {
		     ID => $id,
		     FIRST => $first,
		     LAST => $last,
		    };
    }

    my $template = HTML::Template -> new(filename => 'admin_reassign_job.html');
    $template -> param(PEOPLE => \@people,
		       LOGIN_NAME => $login_name,
		       ID => $job_id);


    print $template -> output();

    return;
  }


  # OK we can go ahead and make the change.

  $dbh -> do ("UPDATE Job SET assigned_person_id=? WHERE id=?",undef,($assign_to,$job_id)) or do {print_bug ($dbh->errstr());return;};

  # If that's OK we should also add a note saying we changed things

  my $changed_to_name = get_name($assign_to);
  my $changed_by_name = get_name($user_id);

  $dbh -> do ("INSERT INTO Note (job_id,text,person_id,private,date,email_sent) VALUES (?,?,?,0,NOW(),0)", undef,($job_id,"Job assigned to $changed_to_name by $changed_by_name",$user_id)) or do {print_bug($dbh -> errstr());return};

  # Now we can go home.
  print $q->redirect("helpdeskadmin.cgi");

}

sub show_job {

  my $job_id = $q -> param ('job_id');

  unless ($job_id) {
    print_bug("No ID supplied when displaying job");
  }

  my $template = HTML::Template -> new (filename=>'admin_job_view.html');
  $template -> param(LOGIN_NAME=>$login_name);

  # First we print out the header

  my $get_job_details_sth = $dbh -> prepare("SELECT Job.id,Job.public_id,Job.commercial,Job.title,DATE_FORMAT(Job.date_opened,'\%e \%b \%Y'),Job.description,Job.status,Job.assigned_person_id,Person.first_name,Person.last_name,Job.person_id,Person.phone FROM Job,Person WHERE Job.id = ? AND Job.person_id = Person.id");

  $get_job_details_sth -> execute($job_id) or do {print_bug($dbh->errstr());return;};

  my ($fetched_id,$public_id,$commercial,$title,$date,$desc,$status,$assigned_person,$first,$last,$submitter_id,$phone) = $get_job_details_sth -> fetchrow_array();

  unless ($fetched_id) {
    print_bug("No job found for ID \"$job_id\"");
    return;
  }

  my ($cc_count) = $dbh->selectrow_array("SELECT COUNT(*) FROM Cc WHERE job_id=?",undef,($job_id));

  unless (defined $cc_count) {
    print_error($dbh->errstr());
    return;
  }

  $template -> param(
		     ID => $job_id,
		     TITLE => modifyHTML($title),
		     DATE => $date,
		     CC_COUNT => $cc_count,
		     SUMMARY => modifyHTML($desc),
		     USER_FIRST => $first,
		     USER_LAST => $last,
		     USER_PHONE => $phone,
		     USER_ID => $submitter_id,
		     ASSIGNED_ID => $assigned_person,
		     JOB_ID => $job_id,
		     PUBLIC_ID => $public_id,
		     COMMERCIAL => $commercial,
		     );



  # If we're the assigned person and the job is open
  # then we can put up a toolbar

  $status = uc($status);

  if ($status eq 'OPEN') {
    $template -> param(OPEN => 1);
  }

  if ($user_id == $assigned_person) {
    $template -> param(OWNER => 1);
  }

  $template -> param(STATUS => $status);

  my $assigned_name= "Not yet assigned";

  if ($assigned_person) {
    $assigned_name = get_name($assigned_person);
  }

  $template -> param(ASSIGNED_NAME=>$assigned_name);


  # If this is a commercial job then if it is assigned, only the
  # assigned person is allowed to view it

#  if ($commercial and $assigned_person and ($user_id != 1 and $assigned_person != $user_id)) {
#    print_error("This is a commercial job and can only be viewed by the assigned person ($assigned_name)");
#    return;
#  }



  # Now we print any notes which have been added to the job

  my @notes;

  my $get_notes_sth = $dbh -> prepare("SELECT Note.id,DATE_FORMAT(Note.date,'\%e \%b \%Y'),Note.text,Note.private,Person.first_name,Person.last_name,Note.email_sent, Note.time FROM Note,Person WHERE Note.job_id=? AND Note.person_id=Person.id ORDER BY Note.date desc");

  $get_notes_sth -> execute($job_id) or do {print_bug ($dbh ->errstr());return;};

  # We should also set up a sth for any files which
  # may have been added to a note

  my $get_files_sth = $dbh -> prepare("SELECT name,id from File WHERE note_id=?");


  while (my ($note_id,$date,$text,$private,$first,$last,$email_sent,$time) = $get_notes_sth -> fetchrow_array()) {

    # To distinguish zero hours and no time we need to change the
    # time to be 0.0 if it's actually numberical zero otherwise 
    # it's just all false in the template check.

    $time = "0.0" if (defined $time and $time == 0);

    my %note = (ID => $note_id,
		DATE => $date,
		PRIVATE => $private,
		TEXT => modifyHTML($text),
		FIRST => $first,
		LAST => $last,
		EMAIL_SENT => $email_sent,
		TIME => $time,
	       );


    $get_files_sth ->execute($note_id) or do {print_bug ($dbh->errstr);return;};

    my @files;
    while (my ($realname,$file_id) = $get_files_sth -> fetchrow_array()) {
      push @files => {ID=> $file_id,
		      NAME => $realname,
		      URI_NAME => uri_escape($realname)};
    }

    $note{files} = \@files;

    push @notes, \%note;
  }

  $template->param(NOTES=>\@notes);

  print $template->output();

}

sub save_job {

  my $job_id = $q -> param ('job_id');

  unless ($job_id) {
    print_bug("No ID supplied when displaying job");
  }

  my $template = HTML::Template -> new (filename=>'job_save.html');

  # First we print out the header

  my $get_job_details_sth = $dbh -> prepare("SELECT Job.id,Job.public_id,Job.commercial,Job.title,DATE_FORMAT(Job.date_opened,'\%e \%b \%Y'),Job.description,Job.status,Job.assigned_person_id,Person.first_name,Person.last_name,Job.person_id,Person.phone FROM Job,Person WHERE Job.id = ? AND Job.person_id = Person.id");

  $get_job_details_sth -> execute($job_id) or do {print_bug($dbh->errstr());return;};

  my ($fetched_id,$public_id,$commercial,$title,$date,$desc,$status,$assigned_person,$first,$last,$submitter_id,$phone) = $get_job_details_sth -> fetchrow_array();

  unless ($fetched_id) {
    print_bug("No job found for ID \"$job_id\"");
    return;
  }


  $template -> param(
		     TITLE => modifyHTML($title),
		     DATE => $date,
		     SUMMARY => modifyHTML($desc),
		     USER_FIRST => $first,
		     USER_LAST => $last,
		     USER_PHONE => $phone,
		     );

  my $zip = Archive::Zip->new();
  $zip -> addDirectory ("$public_id/");
  $zip -> addDirectory ("$public_id/Files/");

  # If we're the assigned person and the job is open
  # then we can put up a toolbar

  $status = uc($status);

  $template -> param(STATUS => $status);

  my $assigned_name= "Not yet assigned";

  if ($assigned_person) {
    $assigned_name = get_name($assigned_person);
  }

  $template -> param(ASSIGNED_NAME=>$assigned_name);


  # If this is a commercial job then if it is assigned, only the
  # assigned person is allowed to view it

  if ($commercial and $assigned_person and $assigned_person != $user_id) {
    print_error("This is a commercial job and can only be viewed by the assigned person ($assigned_name)");
    return;
  }


  # Now we print any notes which have been added to the job

  my @notes;

  # Remember which file names we've seen so we can avoid duplications
  my %seen_files;

  my $get_notes_sth = $dbh -> prepare("SELECT Note.id,DATE_FORMAT(Note.date,'\%e \%b \%Y'),Note.text,Note.private,Person.first_name,Person.last_name,Note.email_sent FROM Note,Person WHERE Note.job_id=? AND Note.person_id=Person.id AND Note.private=0 ORDER BY Note.date");

  $get_notes_sth -> execute($job_id) or do {print_bug ($dbh ->errstr());return;};

  # We should also set up a sth for any files which
  # may have been added to a note

  my $get_files_sth = $dbh -> prepare("SELECT name,location,id from File WHERE note_id=?");


  while (my ($note_id,$date,$text,$private,$first,$last,$email_sent) = $get_notes_sth -> fetchrow_array()) {

    my %note = (ID => $note_id,
		DATE => $date,
		TEXT => modifyHTML($text),
		FIRST => $first,
		LAST => $last,
	       );


    $get_files_sth ->execute($note_id) or do {print_bug ($dbh->errstr);return;};

    my @files;
    while (my ($realname,$location,$file_id) = $get_files_sth -> fetchrow_array()) {
      my $prepend = 0;

      my $usedname = $realname;

      while (exists $seen_files{$usedname}) {
	++$prepend;
	$usedname = "${prepend}_$realname";
      }

      $seen_files{$usedname} = 1;

      my $file_contents;
      open (GUNZIP,"/bin/zcat $location |") or do {print_header();print_bug("Can't gunzip ID $file_id: $!");return;};

      binmode GUNZIP;

      $file_contents .= $_ while (<GUNZIP>);

      $zip->addString($file_contents,"$public_id/Files/$usedname");


      push @files => {
		      NAME=>$usedname,
		      URI_NAME => uri_escape($usedname)};
    }

    $note{files} = \@files;

    push @notes, \%note;
  }

  $template->param(NOTES=>\@notes);

  $zip->addString ($template->output(),"$public_id/job_summary.html");

  print "Content-type: application/zip\n\n";

  $zip->writeToFileHandle(*STDOUT,0);

}

sub get_name {

  # Gets the real name for a person id

  my ($id) = @_;

  my ($first,$last) = $dbh -> selectrow_array("SELECT first_name,last_name FROM Person WHERE id=?",undef,$id);

  if ($first and $last) {
    return("$first $last");
  } else {
    return("Unknown");
  }

}

sub get_email {

  # Gets the email for a person id

  my ($id) = @_;

  my ($email) = $dbh -> selectrow_array("SELECT email FROM Person WHERE id=?",undef,$id);

  if ($email) {
    return($email);
  } else {
    return("Unknown");
  }

}


sub start_new_job {

  # Just put out a form for the person to fill in
  # so we can get what we need to make a new job.

  my $template = HTML::Template -> new (filename => 'admin_new_job.html');


  # We may have been passed a public id from a job
  # to which this is a followup.

  my $job_id = $q -> param('job_id');

  if ($job_id) {

    if ($job_id !~ /^\d+$/) {
      print_bug("Followup job id '$job_id' wasn't a number");
      return;
    }

    # We now need to retrieve the public id and the user
    # email from the previous job to add to the new one.

    my ($public_id,$email) = $dbh->selectrow_array("SELECT Job.public_id, Person.email FROM Job,Person WHERE Job.id=? AND Job.person_id=Person.id",undef,($job_id));

    unless ($public_id) {
      print_bug("Couldn't get details for followup to previous job '$job_id': ".$dbh->errstr());
      return;
    }

    $template -> param(PUBLIC_ID => $public_id,
		       EMAIL => $email);

  }

  $template -> param(LOGIN_NAME => $login_name);

  print $template -> output();

}

sub complete_new_job {

  # This sub takes a completed job request, checks it
  # out and adds the appropriate entry to the database

  my $email = lc($q -> param('email'));

  unless ($email) {
    print_error ("No email address was supplied");
    return;
  }

  unless ($email =~ /^.+\@[\w\-\.]+$/){
    print_error("Email address doesn't look right");
    return;
  }

  my $title = $q -> param('title');


  unless ($title) {
    print_error ("No job title was supplied");
    return;
  }

  $title = $q -> escapeHTML($title);

  my $commercial = $q->param("commercial");

  if ($commercial) {
    $commercial = 1;
  }
  else {
    $commercial = 0;
  }

  my $description = $q -> param('description');

  unless ($description) {
    print_error ("No job description was supplied");
    return;
  }

  $description = $q -> escapeHTML($description);

  # Now we need to know whether the person referenced
  # exists in our database already

  my $person_id = lookup_person_id($email);

  unless ($person_id) {

    my $template = HTML::Template -> new (filename => 'admin_new_person.html');

    # We want to warn people about inadvertently using old
    # bbsrc email addresses and accidentally creating duplicate
    # entries

    my $email_warning = 0;
    if ($email =~ /bbsrc\.ac\.uk$/i) {
      $email_warning = 1;
    }

    $template -> param(LOGIN_NAME => $login_name,
		       EMAIL_WARNING => $email_warning,
		       EMAIL => $email,
		       TITLE => $title,
		       DESCRIPTION => $description,
		       COMMERCIAL => $commercial,
		      );

    print $template -> output();
    return;

  }

  # Right, the person exists so we can create the job

  # We need a job identifier
  my $identifier = make_job_identifier();

  # And now we can make the job
  $dbh -> do("INSERT INTO Job (public_id,person_id,title,description,status,commercial,date_opened) VALUES (?,?,?,?,?,?,NOW())",undef,($identifier,$person_id,$title,$description,'open',$commercial)) or do {print_bug $dbh->errstr(); return};

  # We might want to send them an email confirming the
  # new job creation.

  if ($q->param('send_email')) {

    my $email_message = <<"END_EMAIL_MESSAGE";

Your Bioinformatics support request "$title" has been received and should be acted on in the near future.

You job has been assigned an identifier which allows you to check on it\'s progress using the helpdesk system on the intranet.

The identifier for your job is:

   "$identifier"

You can enter this identifier into the helpdesk system yourself or you can access you job details directly at the following location:

http://www.bioinformatics.babraham.ac.uk/cgi-bin/helpdeskuser.cgi?action=show_job&public_id=$identifier

If you have any queries about any of this then please contact any member of the bioinformatics group.

END_EMAIL_MESSAGE

  send_email($email,'simon.andrews@babraham.ac.uk',"[OPEN] $title",$email_message);

  }

  # Send us back to the home page:

  print $q->redirect("helpdeskadmin.cgi");

}

sub make_job_identifier {

  # This sub makes a unique identifier for
  # each job which is returned to the
  # user.

  open (IN,'/data/private/www/other-bin/Words/clean_words.txt') or die $!;

  my @words;

  while (<IN>) {

    chomp;
    next unless length($_) == 4 or length($_)==5;

    push (@words,lc($_));

  }

  close(IN);

  my $first_word = $words[int(rand($#words))];
  my $second_word = $words[int(rand($#words))];


  return("$first_word$second_word");


}

sub new_job_with_details {


  # This is a routine to take a job + personal details
  # and just extract the personal details to make an
  # entry for them before continuing.

  my $email = $q -> param('email');

  unless ($email) {
    print_error ("No email address was supplied");
    return;
  }

  unless ($email =~ /^.+\@[\w\-\.]+$/){
    print_error("Email address doesn't look right");
    return;
  }

  # We'd better check that they really don't exist
  if (lookup_person_id ($email)) {
    complete_new_job();
    return;
  }


  # If not then we get the rest of the
  # details and make them an entry.

  my $first = $q->param('first_name');

  unless ($first) {
    print_error ("No First Name was supplied");
    return;
  }

  $first = $q -> escapeHTML($first);

  my $last = $q->param('last_name');

  unless ($last) {
    print_error ("No Last Name was supplied");
    return;
  }

  $last = $q -> escapeHTML($last);


  my $phone = $q->param('phone');

  unless ($phone) {
    print_error ("No Phone Number was supplied");
    return;
  }

  $phone = $q -> escapeHTML($phone);

  # OK we've got everything, let's make an entry

  $dbh -> do ("INSERT INTO Person (first_name,last_name,email,phone) VALUES (?,?,?,?)",undef,($first,$last,$email,$phone)) or do {print_bug $dbh -> errstr();return};

  # Now we pass them back to the job completion
  complete_new_job();

}

sub lookup_person_id {

  # Takes an email address and returns a
  # person ID if they are known already

  my ($email) = @_;

  my ($id) = $dbh -> selectrow_array("SELECT id FROM Person WHERE email=?",undef,$email);

  if (defined ($id)) {
    return($id);
  } else {
    return(0);
  }

}

sub close_job {

  # Changes the status of a job to being closed.

  my $job_id = $q -> param('job_id');

  unless($job_id){
    print_bug("No job ID supplied when closing job");
    return;
  }

  my $magnitude = $q->param('level');

  unless (defined $magnitude) {
    my $template = HTML::Template -> new(filename => 'admin_close_job.html');

    my $duration_sth = $dbh->prepare("SELECT id,name FROM Duration");

    $duration_sth->execute() or do {
      print_bug("Failed to get list of durations:".$dbh->errstr());
      return;
    };

    my @duration;

    while (my ($duration_id,$duration_name) = $duration_sth->fetchrow_array()) {
      push @duration,{DURATION_ID => $duration_id,DURATION_NAME=>$duration_name};
    }

    # Get any note times the user has recorded when they did the job.
    my $time_sth = $dbh -> prepare("SELECT DATE_FORMAT(date,'\%e \%b \%Y'),time FROM Note where job_id=? AND time IS NOT NULL");

    $time_sth -> execute($job_id) or do {
	print_bug("Couldn't get times for job $job_id ". $dbh->errstr());
	return;
    };

    my @times;
    my $total_time = 0;

    while (my ($date,$time) = $time_sth -> fetchrow_array()) {
	push @times,{DATE => $date,TIME => $time};
	$total_time += $time;
    }


    $template -> param(
		       LOGIN_NAME => $login_name,
		       ID => $job_id,
		       DURATION => \@duration,
	               TIMES => \@times,
                       TOTAL_TIME => $total_time,
		      );

    print $template->output();
    return;
  }

  unless ($magnitude =~ /^\d+$/ and $magnitude >=0 and $magnitude <=10) {
    print_bug ("Incorrect value '$magnitude' for magnitude when closing job");
    return;
  }

  # Now we need to check that the person closing
  # the job is the current owner.

  my ($job_owner,$owner_email,$current_status) = $dbh -> selectrow_array("SELECT Job.assigned_person_id,Person.email,Job.status FROM Job,Person WHERE Job.id=? AND Job.assigned_person_id=Person.id",undef,$job_id) or do {print_bug ($dbh -> errstr);return;};

  unless ($job_owner == $user_id){
    print_bug ("Only the current job owner can close a job");
    return;
  }

  if ($current_status eq 'closed') {
    print_error("Job is already closed");
    return;
  }

  my $send_email = 0;
  if ($q->param('send_email')) {$send_email=1}

  my $user_name = get_name($user_id);

  # Get the duration assigned to the job.
  my ($duration_name) = $dbh->selectrow_array("SELECT name FROM Duration WHERE id=?",undef,($magnitude));


  # We need to add a note saying that the job was closed
  $dbh->do ("INSERT INTO Note (job_id,text,person_id,private,date,email_sent) VALUES (?,?,?,0,NOW(),?)",undef,($job_id,"Job closed by $user_name with duration $duration_name",$user_id,$send_email)) or do {print_bug ($dbh->errstr());return;};


  # Now we can actually close the job
  $dbh -> do("UPDATE Job SET status='closed',date_closed=NOW(), magnitude=? WHERE id=?",undef,($magnitude,$job_id)) or do {print_bug ($dbh -> errstr());return};


  # We want to send them an email confirming the
  # job closure, but we'll also need to collect
  # some details of the submitter.

  my ($email,$identifier,$title,$commercial) = $dbh->selectrow_array("SELECT Person.email,Job.public_id,Job.title,Job.commercial FROM Job,Person WHERE Job.id=? AND Job.person_id=Person.id",undef,$job_id) or do {print_bug($dbh->errstr());return;};

  my $email_message = <<"END_EMAIL_MESSAGE";

Your Bioinformatics support request "$title" has been completed.

You can use the link below to read the final report on your job.

http://www.bioinformatics.babraham.ac.uk/cgi-bin/helpdeskuser.cgi?action=show_job&public_id=$identifier

If you have any queries about any of this then please contact any member of the bioinformatics group.

END_EMAIL_MESSAGE

  if ($send_email) {

    # Make a list of the people we're going to send this to
    my @recipiants = ($email);

    # Add in any cc's

    my $cc_sth = $dbh->prepare("SELECT Person.email FROM Person,Cc WHERE Cc.job_id=? AND Cc.person_id=Person.id");
    $cc_sth->execute($job_id) or do {
      print_bug("Failed to get cc list for '$job_id': ".$dbh->errstr());
      return;
    };

    while (my ($cc_email) = $cc_sth->fetchrow_array()) {
      push @recipiants,$cc_email;
    }

    if (@recipiants > 10) {
      print_error("More than 10 cc's isn't allowed");
      return;
    }


    foreach my $recipiant (@recipiants) {
      send_email($recipiant,$owner_email,"[CLOSED] $title",$email_message);
    }
  }

  # If this is a chargeable job we also want to send an email from accounts asking
  # for the project code for this job so they can be charged.

  $email_message = <<"END_EMAIL_MESSAGE";

The bioinformatics group recently completed a job for you entitled "$title".  In order to track these jobs we would appreciate it if you could let us know to which project this job relates.  Can you therefore please reply to this message and fill in the line below:

Project number for job "$identifier" is:

Many thanks

Kathryn Umande

END_EMAIL_MESSAGE

  # We only want to send this message if we opted to send emails
  # and if the job is chargeable and if the user is a bbsrc person
  # otherwise we let them sort this out in accounts.

  # 16-01-13 This is causing us such grief that I'm stopping sending these.
  #
  # if ($send_email and $magnitude > 1 and $email =~ /\@babraham.ac.uk$/i and !$commercial) {
  #   send_email($email,'kathryn.umande@babraham.ac.uk',"Re: Your recent bioinformatics job",$email_message);
  # }



  # After closing we can send them back to their job list
  print $q->redirect("helpdeskadmin.cgi");

}

sub start_add_note {

  # This spits out the form to start adding a new
  # note to a job.

  my $template = HTML::Template -> new (filename => 'admin_add_note.html');

  my $job_id = $q -> param('job_id');

  unless ($job_id) {
    print_bug("No job ID supplied when adding note");
    return;
  }

  my $files = $q -> param('files');

  unless ($files) {
    print_bug("No number of files passed when adding note");
    return;
  }

  my $existing_text = $q -> param('text');
  $existing_text = "" unless ($existing_text);
  my $time = $q -> param('time');

  my $send_email = $q->param('send_email');

  my $private = $q->param('private');

  $template -> param (ID => $job_id,
		      TEXT => $existing_text,
		      SEND_EMAIL => $send_email,
		      PRIVATE => $private,
		      TIME => $time,
		     );

  my @files;

  for (1..$files) {

    push @files, {
		  NAME => "file$_",
		 };
  }

  ++$files;

  $template -> param (FILES => \@files,
		      FILE_NUMBER => $files);


  print $template-> output();

}


sub finish_add_note {

  # This finishes off adding a note to a job (optionally
  # with an attached file as well).

  # Let's collect the information we need.

  my $job_id = $q -> param('job_id');

  unless ($job_id) {
    print_bug ("No job ID supplied when finishing note");
    return;
  }

  my $text = $q -> param('text');

  unless ($text) {
    print_error ("No note text supplied");
    return;
  }

  my $send_email = $q->param('send_email');
  if ($send_email) {
    $send_email = 1;
  }
  else {
    $send_email = 0;
  }
  my $keep_private = $q->param('private');
  $keep_private = 0 unless ($keep_private);
  $keep_private = 1 if ($keep_private);

  my $time = $q->param('time');

  if (defined $time and $time ne '') {
      unless ($time =~ /^\d+\.?\d*$/) {
	  print_error("The time value must be blank or be a number, not '$time'");
	  return;
      }
  }
  else {
      $time = undef;
  }


  if ($send_email and $keep_private) {
    print_error("You can't send an email after adding a private note");
    return;
  }

  $text = $q -> escapeHTML($text);

  # Now we can create the note

  $dbh -> do ("INSERT INTO Note (job_id,text,person_id,private,date,email_sent,time) VALUES (?,?,?,?,NOW(),?,?)",undef,($job_id,$text,$user_id,$keep_private,$send_email,$time)) or do{print_bug ($dbh->errstr());return;};

  # Later we may need to know what the Note ID is for
  # the note we just created.

  my ($note_id) = $dbh -> selectrow_array("SELECT LAST_INSERT_ID()");

  unless ($note_id) {
    print_bug("Couldn't get ID of last inserted note");
    return;
  }


  # Now we want to add in any file which
  # was attached

  my $number_of_files = $q->param('files');

  unless ($number_of_files && ($number_of_files =~/^\d+$/)){
    print_bug ("Unusual value '$number_of_files' passed as the number of files");
    return;
  }
  $number_of_files --;

  my @files;

  for (1..$number_of_files){

    push (@files,$q -> param ("file$_"));

  }
  if (@files) {

    # Now loop through the files

    my $file_count = 0;
    foreach my $file (@files) {
      ++$file_count;
      next unless ($file);

      # Strip leading path information (anything up to the
      # last / (unix) \ (windows) or : (Mac)
      my $short_filename = $file;
      $short_filename =~ s/^.*[\\\/:]//;

      # Just in case anything screws up
      unless ($short_filename) {
	print_bug ("No filename left after stripping the path from '$file'");
	return;
      }

      # Now we need to make a File entry
      $dbh -> do ("INSERT INTO File (note_id,name) VALUES (?,?)",undef,($note_id,$short_filename)) or do{print_bug ($dbh->errstr());return;};

      # And then get the insert id for this file

      my ($file_id) = $dbh -> selectrow_array("SELECT LAST_INSERT_ID()");

      unless ($file_id) {
	print_bug("Couldn't get ID of last inserted file");
      }

      # Now we need to actually save the data from the file
      # somewhere.

      # We're going to put all files for a given year into the
      # same directory, so we need to check it exists

      my $this_year = (localtime())[5] + 1900;

      unless (-e "/data/private/helpdesk/$this_year") {
	mkdir ("/data/private/helpdesk/$this_year") or do {print_bug ("Can't create new year dir for file:$!");return};
      }

      my $fh = $q-> upload("file$file_count");

      open (GZIP,"| /bin/gzip > /data/private/helpdesk/$this_year/$file_id") or do {print_bug ("Error piping to gzip:$!");return;};

      binmode GZIP;
      binmode $fh;

      print GZIP while (<$fh>);

      close GZIP or do {print_bug("Error writing to zip file: $!");return;};

      # Now to update the database with the new location

      $dbh -> do ("UPDATE File SET location=? WHERE id=?", undef,("/data/private/helpdesk/$this_year/$file_id",$file_id)) or do {print_bug($dbh->errstr());return;};
    }
  }



  if ($send_email) {

    # We're going to need the public id of the job
    my ($email,$title,$identifier) = $dbh->selectrow_array("SELECT Person.email,Job.title,Job.public_id FROM Job,Person WHERE Job.id=? AND Job.person_id = Person.id",undef,($job_id)) or do {
      print_bug("Couldn't get the public id for job '$job_id'".$dbh->errstr());
      return;
    };

    # We're also going to need the email address of the person
    # adding the note.

    my ($sender_email) = $dbh->selectrow_array("SELECT email from Person WHERE id=?",undef,($user_id));
    unless ($sender_email) {
      print_bug("Couldn't get sender's email for id '$user_id'".$dbh->errstr());
      return;
    }


    # Make a list of the people we're going to send this to
    my @recipiants = ($email);

    # Add in any cc's

    my $cc_sth = $dbh->prepare("SELECT Person.email FROM Person,Cc WHERE Cc.job_id=? AND Cc.person_id=Person.id");
    $cc_sth->execute($job_id) or do {
      print_bug("Failed to get cc list for '$job_id': ".$dbh->errstr());
      return;
    };

    while (my ($cc_email) = $cc_sth->fetchrow_array()) {
      push @recipiants,$cc_email;
    }


    my $email_message = <<"END_EMAIL_MESSAGE";

Your Bioinformatics support request "$title" has been updated.

The identifier for your job is:

   "$identifier"

You can enter this identifier into the helpdesk system yourself or you can access you job details directly at the following location:

http://www.bioinformatics.babraham.ac.uk/cgi-bin/helpdeskuser.cgi?action=show_job&public_id=${identifier}#NOTE$note_id

If you have any queries about any of this then please contact any member of the bioinformatics group.

END_EMAIL_MESSAGE

  if (@recipiants > 10) {
    print_error("Too many recipiants!");
    return;
  }

    foreach my $recipiant (@recipiants) {
      send_email($recipiant,$sender_email,"[UPDATED] $title",$email_message);
    }

  }

  # Now we can send them to the new note

  print $q->redirect("helpdeskadmin.cgi?action=show_job&job_id=${job_id}#NOTE$note_id");

}

sub show_cc {

  # Lists the current cc's for a job

  my $template = HTML::Template -> new (filename => 'admin_show_cc.html');

  my $job_id = $q -> param('job_id');

  unless ($job_id) {
    print_bug("No job ID supplied when showing cc");
    return;
  }

  my $cc_sth = $dbh->prepare("SELECT Cc.id,Person.email FROM Cc,Person WHERE Cc.job_id=? AND Cc.person_id=Person.id ORDER BY Person.email");

  $cc_sth->execute($job_id) or do {
    print_error("Can't list ccs for job $job_id: ".$dbh->errstr());
    return;
  };

  my @cc;

  while (my ($id,$email) = $cc_sth->fetchrow_array()) {
    push @cc,{cc_id => $id, email=>$email};
  }


  $template -> param (JOB_ID => $job_id,
		      CCS => \@cc,
		     );


  print $template-> output();

}


sub add_cc {

  # This adds a new CC address to a job

  # Let's collect the information we need.

  my $job_id = $q -> param('job_id');

  unless ($job_id) {
    print_bug ("No job ID supplied when adding CC");
    return;
  }

  my $email = $q -> param('email');

  unless ($email) {
    print_error ("No email address supplied");
    return;
  }

  # First get the person_id for this email

  my ($person_id) = $dbh->selectrow_array("SELECT id from Person WHERE email=?",undef,($email));

  unless ($person_id) {
    print_error("Couldn't find a person with an email of '$email'");
    return;
  }

  # Check that this person isn't already cc'd to this job
  my ($cc_id) = $dbh->selectrow_array("SELECT id from Cc WHERE job_id=? and person_id=?",undef,($job_id,$person_id));

  if ($cc_id) {
    print_error("$email is already cc'd on this job");
    return;
  }

  # Now we can add the cc

  $dbh -> do ("INSERT INTO Cc (job_id,person_id) VALUES (?,?)",undef,($job_id,$person_id)) or do{print_bug ($dbh->errstr());return;};


  # Now we can send them back to the cc list

  print $q->redirect("helpdeskadmin.cgi?action=show_cc&job_id=$job_id");

}

sub remove_cc {

  # This removes a CC address from a job

  # Let's collect the information we need.

  my $cc_id = $q -> param('cc_id');

  unless ($cc_id) {
    print_bug ("No cc ID supplied when adding CC");
    return;
  }

  # Check this exists and which job it came from
  my ($job_id) = $dbh->selectrow_array("SELECT job_id FROM Cc WHERE id=?",undef,($cc_id));

  unless ($job_id) {
    print_bug("Couldn't find cc with id $cc_id:". $dbh->errstr());
    return;
  }

  # Now do the deletion
  $dbh->do("DELETE from Cc where id=?",undef,($cc_id)) or do {
    print_bug("Unable to delete cc :".$dbh->errstr());
    return;
  };

  print $q->redirect("helpdeskadmin.cgi?action=show_cc&job_id=$job_id");

}


sub send_file {

  # Returns a file which was previously stored

  my $file_id = $q -> param('file_id');

  # We need to get the original name and current
  # location of the file.

  my ($name,$location) = $dbh -> selectrow_array("SELECT name,location FROM File WHERE id=?",undef,$file_id);

  unless ($name) {
    print_header();
    print_bug ("Couldn't get name for file $file_id");
    return;
  }

  my $mime_type = 'text/plain';

  my %overridden_types = (
			  docx => 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
			  pptx => 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
			  xlsx => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
			  pl => 'text/plain',
                          sh => 'text/plain',
			  pzfx => 'application/x-graphpad-prism-pzfx',
			 );

  if ($name =~ /\.(\w+)$/) {
    my $extension = lc($1);

    if (exists $overridden_types{$extension}) {
      $mime_type = $overridden_types{$extension};
    }
    else {

      open (MIME,'/etc/mime.types') or do{print_header();print_bug("Can't open MIME type file: $!"); return;};

    TYPES: while (<MIME>) {
	chomp;
	my ($type,@exts) = split(/\s+/);
	next unless ($exts[0]);
	
	foreach my $ext (@exts){
	  if ($ext eq $extension) {
	    $mime_type = $type;
	    last TYPES;
	  }
	}
      }

      close MIME;
    }
  }


  open (GUNZIP,"/bin/zcat $location |") or do {print_header();print_bug("Can't gunzip ID $file_id: $!");return;};

  binmode GUNZIP;

  print "Content-type: $mime_type\n\n";

  print while (<GUNZIP>);

  close GUNZIP;

}

sub show_person {

  # Shows a persons details and allows us to change
  # them.

  my $person_id = $q -> param('person_id');

  unless ($person_id) {
    print_bug ("No person id supplied when showing person details");
    return;
  }

  my $job_id = $q -> param('job_id');

  unless ($job_id) {
    print_bug ("No referring job id supplied when showing person details");
    return;
  }

  # Now we can get the details we need.

  my ($fetched_id,$first,$last,$email,$phone) = $dbh-> selectrow_array("SELECT id,first_name,last_name,email,phone FROM Person WHERE id=?",undef,$person_id) or do {print_bug($dbh->errstr);return};

  unless ($fetched_id) {
    print_bug("No details found for person id '$person_id'");
    return;
  }


  my $template;

  my $edit = $q-> param('edit');

  if ($edit) {

    $template = HTML::Template -> new (filename => 'admin_edit_person.html');

  }
  else {
    $template = HTML::Template -> new (filename => 'admin_show_person.html');
  }

  $template -> param(
		     FIRST => $first,
		     LAST => $last,
		     JOB_ID => $job_id,
		     PERSON_ID => $person_id,
		     EMAIL => $email,
		     PHONE => $phone,
		    );


  print $template -> output();
}


sub update_person {

  # Takes the details from a person change
  # form and applied them to the database.

  my $person_id = $q -> param('person_id');

  unless ($person_id) {
    print_bug ("No person id supplied when changing person details");
    return;
  }

  my $job_id = $q -> param('job_id');

  unless ($job_id) {
    print_bug ("No referring job id supplied when changing person details");
    return;
  }

  # We now need the information they've
  # supplied about the person

  my $first = $q -> param('first_name');

  unless ($first) {
    print_error ("No first name was supplied");
    return;
  }

  my $last = $q -> param('last_name');

  unless ($last) {
    print_error ("No last name was supplied");
    return;
  }

  my $phone = $q -> param('phone');

  unless ($phone) {
    print_error ("No phone number was supplied");
    return;
  }

  # OK we can now do the update..

  $dbh -> do("UPDATE Person SET first_name=?,last_name=?,phone=? WHERE id=?",undef,($first,$last,$phone,$person_id)) or do {print_bug($dbh->errstr());return};

  # and send them back to the person view
    show_person();

}

sub show_search_form {

  # Will need to collect some database info
  # before printing the form

  my $template = HTML::Template -> new(filename=>'admin_search.html');

  # We need to know all the people who can
  # be assigned to
  my $people_sth = $dbh -> prepare("SELECT id,first_name,last_name FROM Person WHERE can_assign_to IS NOT NULL ORDER BY last_name");

  $people_sth -> execute() or do {print_bug($dbh->errstr());return;};

  my @people;


  while (my ($id,$first,$last) = $people_sth -> fetchrow_array()){

   push @people, {ID => $id,
		   FIRST => $first,
		   LAST => $last,
		  };
  }

  $template -> param(
		     PEOPLE => \@people,
		     LOGIN_NAME => $login_name
		    );


  # We also need to give proper
  # year options.

  my @years;

  for (reverse(2003 .. ([localtime()]->[5]+1900))){
    push @years,{YEAR => $_};
  }

  $template -> param(YEARS => \@years);

  print $template -> output();


}


sub run_search {

  # This actually runs a search of the helpdesk
  # system.

  my $template = HTML::Template -> new (filename => 'admin_search_results.html');

  $template -> param(LOGIN_NAME => $login_name);

  # We're actually going to be building up a large
  # SQL command, so we need somewhere to start from.

  my $sql = "SELECT Job.id,Job.public_id,Job.person_id,Job.assigned_person_id,Job.title,DATE_FORMAT(Job.date_opened,'\%e \%b \%Y'),DATE_FORMAT(Job.date_closed,'\%e \%b \%Y'),Job.magnitude, Job.commercial, Job.budget_code from Job,Person WHERE Job.person_id=Person.id";

  # and now we have to add stuff to it.  We will need to know
  # how many items have been added so we can join with the correct
  # operator
  my $found_filter=0;

  # We're also going to be binding stuff, so we need to
  # keep that separate.
  my @bind_values;

  # For multiple pages we're also going to need
  # to recreate the original query, so this will
  # go in a separate string
  my $query = "action=run_search";

  # Job status
  if ($q -> param('status')){
    $found_filter = 1;
    my $status = $q->param('status_option');
    $sql .= " AND Job.status=?";
    $query .="&status=1&status_option=$status";
    push (@bind_values,$status);
  }

  # Job type
  if ($q -> param('commercial')){
    $found_filter = 1;
    my $type = $q->param('commercial_option');
    $sql .= " AND Job.commercial=?";
    $query .="&commercial=1&commercial_option=$type";
    push (@bind_values,$type);
  }

  # Assigned Person
  if ($q -> param('assigned')){
    $found_filter = 1;
    my $assigned_person = $q->param('assigned_person');
    $sql .= " AND Job.assigned_person_id=?";
    $query .="&assigned=1&assigned_person=$assigned_person";
    push (@bind_values,$assigned_person);
  }

  # Submitter
  if ($q -> param('submitter')){

    $found_filter =1;
    $query .="&submitter=1";
    # Since the submitter can be specified
    # in 3 fields we need to know that at
    # least one of them has been filled
    my $found_submitter=0;

    # First Name
    my $first = $q->param('first_name');
    if ($first){
      $found_submitter=1;
      $sql .= " AND Person.first_name=?";
      $query .="&first_name=$first";
      push (@bind_values,$first);
    }

    # Last Name
    my $last = $q->param('last_name');
    if ($last){
      $found_submitter=1;
      $sql .= " AND Person.last_name=?";
      $query .="&last_name=$last";
      push (@bind_values,$last);
    }

    # Email
    my $email = $q->param('email');
    if ($email){
      $found_submitter=1;
      $sql .= " AND Person.email=?";
      $query .="&email=$email";
      push (@bind_values,$email);
    }

    unless($found_submitter) {
      print_error("You filtered on submitter, but provided no submitter details");
      return;
    }

  }

  # Public ID
  if ($q -> param('public_id')){

    my $public_id = $q->param('public_id_value');
    if ($public_id){
      $found_filter =1;
      $query .="&public_id=1";
      $sql .=" AND Job.public_id=?";
      push (@bind_values,$public_id);
    }
  }


  # Job date
  if ($q -> param('date')){
    $found_filter = 1;
    $query .="&date=1";

    my $date_type=$q->param('date_type');

    if ($date_type eq 'last'){

      $query .="&date_type=last";
      my %translate_date = (day => 1,
			    week => 7,
			    month => 31,
			    year => 365);

      my $interval = $q -> param('submitted_interval');
      unless ($interval) {
	print_bug ("No interval supplied for date search");
	return;
      }
      $query .="&submitted_interval=$interval";
      unless (exists($translate_date{$interval})){
	print_bug ("Don't understand date interval '$interval'");
	return;
      }
      $sql .= " AND Job.date_opened >= CURDATE() - INTERVAL $translate_date{$interval} DAY";
    }

    elsif ($date_type eq 'between') {
      my $datefield = $q->param("datefield");

      unless ($datefield) {
	print_bug("No datefield provided when searching between dates");
	return;
      }

      unless ($datefield eq 'opened' or $datefield eq 'closed') {
	print_bug("Unknown datefield '$datefield' provided when searching");
	return;
      }
      $query .="&date_type=between&datefield=$datefield";
      my %months = (
		    Jan => '01',
		    Feb => '02',
		    Mar => '03',
		    Apr => '04',
		    May => '05',
		    Jun => '06',
		    Jul => '07',
		    Aug => '08',
		    Sep => '09',
		    Oct => '10',
		    Nov => '11',
		    Dec => '12'
		   );

      unless (exists ($months{$q->param('month_from')})){
	print_bug ("Incorrect month from information supplied");
	return;
      }

      unless ($q -> param('year_from') =~ /^\d{4}$/){
	print_bug("Incorrect year from information supplied");
	return;
      }

      if ($datefield eq 'opened') {
	$sql .= " AND Job.date_opened >= '".$q->param('year_from')."-".$months{$q->param('month_from')}."-01'";
      }
      elsif ($datefield eq 'closed') {
	$sql .= " AND Job.date_closed >= '".$q->param('year_from')."-".$months{$q->param('month_from')}."-01'";
      }
      else {
	print_bug("Unknown datefield '$datefield' provided when searching");
	return;
      }
      $query .="&year_from=".$q->param('year_from')."&month_from=".$q->param('month_from');

      unless (exists ($months{$q->param('month_to')})){
	print_bug ("Incorrect month to information supplied");
	return;
      }

      unless ($q -> param('year_to') =~ /^\d{4}$/){
	print_bug("Incorrect year to information supplied");
	return;
      }
      $query .="&year_to=".$q->param('year_to')."&month_to=".$q->param('month_to');

      # We construct the end by going to the 1st of the next month
      # and saying less than that.
      my $end_next_year = $q->param('year_to');
      my $end_next_month = $months{$q->param('month_to')};
      $end_next_month++;
      if ($end_next_month == 13) {
	$end_next_month = 1;
	$end_next_year++;
      }
      # Reformat the month to have two digits
      $end_next_month = sprintf("%02d",$end_next_month);
      

      $sql .= " AND Job.date_$datefield < '".$end_next_year."-".$end_next_month."-01'";
    }

    else {
      print_bug("Don't understand date type '$date_type'");
      return;
    }


  }


  # Job keyword
  if ($q -> param('keyword')){
    $found_filter = 1;
    $query .="&keyword=1";
    my $keyword = $q->param('keyword_data');

    unless ($keyword){
      print_error("No keyword supplied for the keyword filter");
      return;
    }
    $query .="&keyword_data=$keyword";
    $keyword = "\%$keyword\%";

    my $target = $q -> param('keyword_source');

    unless ($target eq 'title' or $target eq 'description') {
      print_bug ("Strange value '$target' for keyword target");
      return;
    }

    $query .= "&keyword_source=$target";

    $sql .= " AND Job.$target LIKE ?";
    push (@bind_values,$keyword);
  }

  $sql .= ' ORDER BY Job.date_opened DESC';

  unless ($found_filter) {
    print_error("No filters were supplied");
    return;
  }

  # We can now try to use the SQL
  my $sth = $dbh -> prepare($sql);

  $sth -> execute(@bind_values) or do {print_bug($dbh->errstr());return;};

  my $search_results = $sth->fetchall_arrayref();

  my $number_of_hits = scalar @$search_results;

  my $page = $q->param('page');
  $page = 1 unless ($page);

  if ($page > 1 and $number_of_hits <= (20*($page-1))){
    print_bug ("No hits available on page $page");
    return;
  }

  my $first_hit_index = ($page-1)*20;
  my $last_hit_index = $first_hit_index + 19;

  $last_hit_index = $number_of_hits-1 if ($last_hit_index > ($number_of_hits-1));

  if ($q->param("showall")) {
    $first_hit_index = 0;
    $last_hit_index = $number_of_hits -1;
  }

  my $first_hit_number = $first_hit_index +1;
  my $last_hit_number = $last_hit_index+1;


  my @hits;

  $template -> param (
		      HIT_START => $first_hit_number,
		      HIT_END => $last_hit_number,
		      HIT_COUNT => $number_of_hits,
		     );

  my $count = 0;

  foreach my $hit (@$search_results){

    unless ($count >= $first_hit_index){
      ++$count;
      next;
    }
    last if ($count > $last_hit_index);

    my ($id,$public_id,$person,$assigned,$title,$opened,$closed,$magnitude,$commercial,$budget) = @$hit;

    my $person_name = get_name($person);
    my $person_email = get_email($person);
    my $assigned_name = "Not assigned";

    if ($assigned){
      $assigned_name=get_name($assigned);
    }

    my $duration;
    if (defined $magnitude) {
      ($duration) = $dbh->selectrow_array("SELECT name FROM Duration WHERE id=?",undef,($magnitude));
    }


    push @hits, {
		 TITLE => $title,
		 SUBMITTER_NAME => $person_name,
		 SUBMITTER_EMAIL => $person_email,
		 ASSIGNED_NAME => $assigned_name,
		 ID => $id,
		 PUBLIC_ID => $public_id,
		 OPENED => $opened,
		 CLOSED => $closed,
		 DURATION => $duration,
		 COMMERCIAL => $commercial,
		 BUDGET_CODE => $budget,
		};

    ++$count;
    #last if ($count == 10);
  }

  $template -> param (HITS => \@hits);

  # Now we put out the links to other pages
  # of results

  my @pages;

  my $last_page = int(($number_of_hits-1)/20)+1;

  if ($last_page > 1){

    for (1..$last_page){

      if ($_ == $page){
	push @pages, {PAGE => $_,
		      SEARCH_PARAMS => $query,
		      CURRENT => 1,
		     };
      }

      else {
	push @pages, {PAGE => $_,
		      SEARCH_PARAMS => $query,
		      CURRENT => 0,
		     };
      }
    }
  }

  $template -> param (PAGES => \@pages);

  print $template -> output();

}


sub send_email {

  my ($email,$from,$title,$message) = @_;

  my %mail = (
	      To => $email,
	      From => $from,
	      Subject => $title,
	      Message => $message,
	     );

  sendmail(%mail) or warn $Mail::Sendmail::error;

}


sub reopen_job {

  # Reopens a job which was previously closed

  # First let's check we've got the info
  # we need.

  my $job_id = $q -> param('job_id');
  unless ($job_id) {
    print_bug("No job id passed when repopening job");
    return;
  }

  unless ($job_id =~ /^\d+$/) {
    print_bug("Invalid job id '$job_id' passed when repopening job");
    return;
  }

  # Let's see if this has been checked and/or assigned
  unless ($q->param('checked')) {
    # We need to spit out a form
    my $template = HTML::Template -> new (filename => 'admin_reopen_job.html');

    my @people;

    my $users_sth = $dbh -> prepare("SELECT first_name,last_name,id FROM Person WHERE can_assign_to='yes' ORDER BY last_name");
    $users_sth -> execute() or do{print_bug($dbh->errstr());return};

    while (my ($first,$last,$id) = $users_sth -> fetchrow_array()) {

      push @people, {
		     ID => $id,
		     FIRST => $first,
		     LAST => $last,
		    };
    }

    $template -> param(
		       LOGIN_NAME => $login_name,
		       ID => $job_id,
		       PEOPLE => \@people,
		      );

    print $template -> output();
    return;
  }

  # See if we're going to assign to anyone
  my $assigned = $q->param('assign');

  if ($assigned) {
    unless ($assigned =~ /^\d+$/) {
      print_bug("Invalid user id '$assigned' when reopening job");
      return;
    }
  }
  else {
    $assigned = undef;
  }

  my $assigned_text;

  if ($assigned) {
    my $name = get_name($assigned);
    unless ($name) {
      print_bug("Assigned id '$assigned' did not map to a known user when repopening a job");
      return;
    }
    $assigned_text = "and assigned to $name";
  }

  else {
    $assigned_text = "but not yet assigned to a member of the bioinformatics group";
  }


  # We need the submitter email to send them a message

  my ($email,$title,$identifier) = $dbh -> selectrow_array("SELECT Person.email,Job.title,Job.public_id from Job,Person WHERE Job.id=? AND Job.person_id=Person.id",undef,$job_id) or do {print_bug $dbh->errstr();return;};

  # OK we can go ahead and make the change.

  $dbh -> do ("UPDATE Job SET status='open',date_closed=null,magnitude=null,assigned_person_id=? WHERE id=?",undef,($assigned,$job_id)) or do {print_bug ($dbh->errstr());return;};

  # If that's OK we should also add a note saying we changed things

  my $changed_by_name = get_name($user_id);

  my $note_text = "Job re-opened by $changed_by_name";
  $note_text .= " $assigned_text" if ($assigned);

  $dbh -> do ("INSERT INTO Note (job_id,text,person_id,private) VALUES (?,?,?,0)", undef,($job_id,$note_text,$user_id)) or do {print_bug($dbh -> errstr());return};

  # We want to send them an email confirming the
  # new job creation.

  my $email_message = <<"END_EMAIL_MESSAGE";

Your Bioinformatics support request "$title" has been re-opened $assigned_text.

The identifier for this job is:

   "$identifier"

You can enter this identifier into the helpdesk system yourself or you can access you job details directly at the following location:

http://www.bioinformatics.babraham.ac.uk/cgi-bin/helpdeskuser.cgi?action=show_job&public_id=$identifier

If you have any queries about any of this then please contact any member of the bioinformatics group.

END_EMAIL_MESSAGE

  if ($q->param("send_email")) {
    send_email($email,'simon.andrews@babraham.ac.uk',"[RE-OPENED] $title",$email_message);
  }

  # If that's it then we can send them home
  print $q -> redirect("helpdeskadmin.cgi");

}

sub modifyHTML {

  # This sub allows us to make replacements in the HTML
  # to allow inteligent linking and other clever stuff...

  my $escaped = shift;

  # Change line breaks for html breaks
  $escaped =~ s/\n/<br>/g;

  # Turn things which look like links into links.
  $escaped =~ s!(https?://\S+)(\w)!make_link($1,$2)!ieg;


  # Turn references to other helpdesk jobs into links to those jobs.
  $escaped =~ s!public_id=(\w+)!public_id=<a href="helpdeskadmin.cgi?action=run_search&amp;public_id=1&amp;public_id_value=$1">$1</a>!g;


  return $escaped;

}

sub make_link {

  my ($text,$following) = @_;

  if ($text =~ /public_id/) {
    return "$text$following";
  }
  else {
    return "<a href=\"$text$following\">$text$following</a>";
  }

}
