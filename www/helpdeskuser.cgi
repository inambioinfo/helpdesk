#!/usr/bin/perl -w
use strict;
use CGI;
use DBI;
use Mail::Sendmail;
use URI::Escape;
use HTML::Template;
use FindBin qw ($Bin);

my $q = CGI->new();

chdir "$Bin/../templates" or die "Can't move to templates directory: $!";

#my $dbh = DBI->connect("DBI:mysql:database=Helpdesk;host=bilin2.babraham.ac.uk","cgiuser","",
#		       {RaiseError=>0,AutoCommit=>1});

my $dbh = DBI->connect("DBI:mysql:database=Helpdesk;host=localhost","cgiuser","",
		       {RaiseError=>0,AutoCommit=>1});

unless ($dbh) {
  print_header();
  print_bug("Couldn't connect to database: ".$DBI::errstr);
  exit;
}

my $action = $q -> param('action');

if ($action) {

  if ($action eq 'show_job') {
    show_job();
  }

  elsif ($action eq 'set_budget') {
    set_budget_code();
  }


  elsif ($action eq 'new_job') {
    start_new_job();
  }

  elsif ($action eq 'complete_new_job') {
    complete_new_job();
  }

  elsif ($action eq 'new_job_with_details') {
    new_job_with_details();
  }

  elsif ($action eq 'send_file') {
    send_file();
  }

  else {
    print_bug("Unknown action \"$action\" called");
  }
}

else {
  show_front_page();
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

  my $template = HTML::Template->new(filename=>'bug.html');
  $template->param(MESSAGE => $bug_message);
  print $template->output();
}

sub print_error {

  # This prints up an error message when it
  # looks like someone has made a user mistake
  # These messages could occur commonly 
  # within the normal running of the script

  my ($error_message) = @_;

  my $template = HTML::Template-> new(filename=>'error.html');

  $template->param(MESSAGE => $error_message);
  print $template->output();


}


sub get_user_id {

  # Translates a username to a database user id

  my $username = $q -> remote_user;

  unless ($username) {
    print_herader();
    print_bug ("Noone appears to be logged in");
  }

  my ($id) = $dbh -> selectrow_array("SELECT id FROM Person WHERE username=?",undef,$username);

  unless ($id) {
    print_header();
    print_bug ("Couldn't get user id for $username");
  }


}



sub show_job {

  my $public_id = $q -> param ('public_id');

  unless ($public_id) {
    print_bug("No ID supplied when displaying job");
    return;
  }

  my $get_job_details_sth = $dbh -> prepare("SELECT Job.id,Job.title,DATE_FORMAT(Job.date_opened,'\%e \%b \%Y'),Job.description,Job.status,Job.assigned_person_id,Person.first_name,Person.last_name,Person.phone,Job.budget_code FROM Job,Person WHERE Job.public_id = ? AND Job.person_id = Person.id");

  $get_job_details_sth -> execute($public_id) or do {print_bug($dbh->errstr());return;};

  my ($job_id,$title,$date,$desc,$status,$assigned_person,$first,$last,$phone,$budget) = $get_job_details_sth -> fetchrow_array();

  unless ($job_id) {
    print_error("No job found for ID \"$public_id\"");
    return;
  }

  $desc =~ s/[\n]/<br>/g;

  $status = uc($status);

  my $assigned_name;

  if ($assigned_person){
    $assigned_name = get_name($assigned_person);
  }

  my $template = HTML::Template->new(filename => 'job_view.html');

  $template -> param(USER_FIRST => $first,
		     USER_LAST => $last,
		     USER_PHONE => $phone,
		     DATE => $date,
		     STATUS => $status,
		     ASSIGNED_NAME => $assigned_name,
		     TITLE => modifyHTML($title),
		     SUMMARY => modifyHTML($desc),
		     BUDGET_CODE => $budget,
		    );

  # Now we print any notes which have been added to the job

  my @notes;

  my $get_notes_sth = $dbh -> prepare("SELECT Note.id,DATE_FORMAT(Note.date,'\%e \%b \%Y'),Note.text,Person.first_name,Person.last_name FROM Note,Person WHERE Note.job_id=? AND Note.private != 1 AND Note.person_id=Person.id ORDER BY Note.date");

  $get_notes_sth -> execute($job_id) or do {print_bug ($dbh ->errstr());return;};

  # We should also set up a sth for any files which
  # may have been added to a note

  my $get_files_sth = $dbh -> prepare("SELECT name,id from File WHERE note_id=?");


  while (my ($note_id,$date,$text,$first,$last) = $get_notes_sth -> fetchrow_array()){

    $text =~ s/[\n]/<br>/g;


    $get_files_sth ->execute($note_id) or do {print_bug ($dbh->errstr);return;};

    my @files;

    while (my ($realname,$file_id) = $get_files_sth -> fetchrow_array()){
      push @files, {
		    ID => $file_id,
		    NAME => $realname,
		    URI_NAME => uri_escape($realname),
		    PUBLIC_ID => $public_id,
		   };
    }


    push @notes, {
		  ID => $note_id,
		  DATE => $date,
		  FIRST => $first,
		  LAST => $last,
		  TEXT => modifyHTML($text),
		  FILES => \@files,
		 };


  }
  $template -> param(NOTES => \@notes);

  print $template -> output();

}

sub get_name {

  # Gets the real name for a person id

  my ($id) = @_;

  my ($first,$last) = $dbh -> selectrow_array("SELECT first_name,last_name FROM Person WHERE id=?",undef,$id);

  if ($first and $last){
    return("$first $last");
  }

  else {
    return("Unknown");
  }

}


sub start_new_job {

  # Just put out a form for the person to fill in
  # so we can get what we need to make a new job.

  my $template = HTML::Template -> new (filename => 'new_job.html');
  print $template ->output();
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

  my $description = $q -> param('description');

  unless ($description) {
    print_error ("No job description was supplied");
    return;
  }

  $description = $q->escapeHTML($description);

  # We're assuming that jobs opened by the public interface
  # will never be commercial.
  my $commercial = 0;

  # Now we need to know whether the person referenced
  # exists in our database already

  my $person_id = lookup_person_id($email);

  unless ($person_id) {

    # We don't let the public interface open jobs with
    # bbsrc.ac.uk emails now that everyone should have
    # moved to a babraham.ac.uk address

    if ($email =~ /bbsrc\.ac\.uk$/) {
      print_error("You can't open new jobs with bbsrc.ac.uk email addresses. Please use the new babraham.ac.uk version");
      return;
    }

    my $template = HTML::Template -> new (filename => 'new_person.html');
    $template -> param(
		       EMAIL => $email,
		       TITLE => $title,
		       DESCRIPTION => $description,
		      );

    print $template -> output();
    return;

  }

  # Right, the person exists so we can create the job

  # We need a job identifier
  my $identifier = make_job_identifier();

  # We need to know if we can assign a budget code
  my @budget_codes = get_valid_budget_list($email);

  my $budget_code_to_use;

  if (@budget_codes) {
      $budget_code_to_use = $budget_codes[0]->{CODE};
  }

  $budget_code_to_use = "" unless ($budget_code_to_use);

  # And now we can make the job
  $dbh -> do("INSERT INTO Job (public_id,person_id,title,description,status,commercial,date_opened,budget_code) VALUES (?,?,?,?,?,?,NOW(),?)",undef,($identifier,$person_id,$title,$description,'open',$commercial,$budget_code_to_use)) or do {print_bug $dbh->errstr(); return};

  # We need to send them an email confirming the
  # new job creation.

  my $email_message = <<"END_EMAIL_MESSAGE";

Your Bioinformatics support request "$title" has been received and should be acted on in the near future.

You job has been assigned an identifier which allows you to check on its progress using the helpdesk system on the intranet.

The identifier for your job is:

   "$identifier"

You can enter this identifier into the helpdesk system yourself or you can access you job details directly at the following location:

http://www.bioinformatics.babraham.ac.uk/cgi-bin/helpdeskuser.cgi?action=show_job&public_id=$identifier

END_EMAIL_MESSAGE

if (@budget_codes) {

    $email_message .= "Your job has been assinged to budget code code\n\n";
    $email_message .= $budget_codes[0]->{CODE} . " (".$budget_codes[0]->{DESCRIPTION}.")\n\n";

    if (@budget_codes > 1) {
	$email_message .= "You can also use one of the budgets listed below.  Click on a link to use that budget instead\n\n";

	for my $index(0..$#budget_codes) {
	    $email_message .= "$budget_codes[$index]->{CODE} http://www.bioinformatics.babraham.ac.uk/cgi-bin/helpdeskuser.cgi?action=set_budget&public_id=$identifier&code=$index\n\n";
	}

    }

    if ($email =~ /babraham.ac.uk/i) {
	$email_message .= "If you don't see the code you want to use listed, please reply to this message with the correct code and we can add it manually\n";
    }
}

$email_message .= <<"END_EMAIL_MESSAGE";

If you have any queries about any of this then please contact any member of the bioinformatics group.
END_EMAIL_MESSAGE

  ## TODO: Remove after testing

#  send_email($email,'simon.andrews@babraham.ac.uk',"[OPEN] $title",$email_message);
  send_email('simon.andrews@babraham.ac.uk','simon.andrews@babraham.ac.uk',"[OPEN] $title",$email_message);

  # And print the confirmation message

  my $template = HTML::Template -> new (filename=>'finish_new_job.html');

  $template -> param(ID=>$identifier);

  print $template -> output();
}

sub set_budget_code {

  # This sub allows a user to change the budget code which was
  # assigned to their job.

  my $public_id = $q -> param('public_id');

  unless ($public_id) {
    print_bug ("No public_id found, can't identify job");
    return;
  }

  # See if we can find a job and a persons email for this public id
  my ($job_id,$email) = $dbh -> selectrow_array("SELECT Job.id, Person.email FROM Job,Person WHERE Job.public_id=? AND Job.person_id=Person.id",undef,($public_id));

  unless ($job_id) {
      print_bug("No job found with public_id $public_id");
      return;
  }

  # Now get the list of budget codes we can choose from
  my @budget_codes = get_valid_budget_list($email);

  unless (@budget_codes) {
      print_bug("Couldn't find any budget codes for $email");
      return;
  }


  # See which one they want to use.
  my $code_index = $q -> param("code");
  unless (defined $code_index) {
      print_bug("No code index found when setting budget codes");
      return;
  }

  unless ($code_index =~ /^\d+$/) {
      print_bug("Code index wasn't a number");
      return;
  }

  if ($code_index > $#budget_codes || $code_index < 0) {
      print_bug "Code index $code_index was an invalid range";
      return;
  }

  # Set the code
  $dbh -> do("UPDATE Job SET budget_code=? where id=?",undef,($budget_codes[$code_index]->{CODE},$job_id)) or do {
      print_bug("Can't set new budget code:".$dbh->errstr());
      return;
  };

  print $q -> redirect("helpdeskuser.cgi?action=show_job&public_id=$public_id");
  return;

}

sub make_job_identifier {

  # This sub makes a unique identifier for
  # each job which is returned to the
  # user.

  open (IN,'/data/private/www/other-bin/Words/clean_words.txt') or die $!;

  my @words;

  while (<IN>){

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
  if (lookup_person_id ($email)){
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

  if (defined ($id)){
    return($id);
  }

  else {
    return(0);
  }

}

sub send_file {

  # Returns a file which was previously stored

  my $file_id = $q -> param('file_id');

  # Because this is being supplied to a public
  # interface they need both the file id and 
  # the public id to get the file.  The file
  # id alone isn't secure as it's just an
  # incrementing number.

  my $public_id = $q -> param('public_id');

  # We need to get the original name and current
  # location of the file.

  my ($name,$location) = $dbh -> selectrow_array("SELECT File.name,File.location FROM File,Note,Job WHERE File.id=? AND File.note_id=Note.id AND Note.job_id=Job.id AND Job.public_id=?",undef,($file_id,$public_id));

  unless ($name) {
    print_bug ("Couldn't get name for file $file_id using public id '$public_id'");
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

      while (<MIME>) {
	chomp;
	my ($type,$ext) = split(/\s+/);
	next unless ($ext);

	if ($ext eq $extension) {
	  $mime_type = $type;
	  last;
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

sub show_front_page {

  my $template = HTML::Template->new(filename=>'home.html');
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


sub modifyHTML {

  # This sub allows us to make replacements in the HTML
  # to allow inteligent linking and other clever stuff...

  my $escaped = shift;

  # Change line breaks for html breaks
  $escaped =~ s/\n/<br>/g;

  # Turn things which look like links into links.
  $escaped =~ s!(http://\S+)(\w)!make_link($1,$2)!ieg;


  # Turn references to other helpdesk jobs into links to those jobs.
  $escaped =~ s!public_id=(\w+)!public_id=<a href="helpdeskuser.cgi?action=show_job&amp;public_id=$1">$1</a>!g;

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

sub get_valid_budget_list {

  my ($email) = @_;

  my $budget_dbh = DBI->connect("DBI:mysql:database=sierra_budget;host=localhost","sierrauser","",{RaiseError=>0,AutoCommit=>1});

  unless ($budget_dbh) {
      print_bug("Couldn't connect to budget database:".$DBI::errstr);
      exit;
  }

  # See what we can find for this email.  If we're not passed an email we return a
  # non-redundant list of every possible code
  my $sth;

  if ($email) {
      $sth = $budget_dbh->prepare("SELECT code,description FROM budget_codes WHERE email=?");
      
      $sth->execute($email) or do {
	  print_bug("Failed to list valid budgets for $email: ".$dbh->errstr());
	  exit;
      };
  }
  else {
      $sth = $budget_dbh->prepare("SELECT code,description FROM budget_codes");
      
      $sth->execute() or do {
	  print_bug("Failed to list all valid budgets: ".$dbh->errstr());
	  exit;
      };
  }

  my @valid_codes;
  my %seen_codes;

  while (my ($code,$description) = $sth->fetchrow_array()) {

      next if (exists $seen_codes{$code});
      $seen_codes{$code}++;
      push @valid_codes, {CODE => $code,
			  DESCRIPTION => $description,};
  }

  return @valid_codes;
}


